import os
import pickle
import urllib.parse as urlparse
from urllib.parse import parse_qs

import re
import time
import json
import errno
import logging

from mimetypes import guess_type
from httplib2 import Http
from google.oauth2 import service_account
from oauth2client.client import OAuth2Credentials, OAuth2WebServerFlow, FlowExchangeError
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from tenacity import *

LOGGER = logging.getLogger(__name__)
logging.getLogger('googleapiclient.discovery').setLevel(logging.ERROR)

# Check https://developers.google.com/drive/scopes for all available scopes
OAUTH_SCOPE = ['https://www.googleapis.com/auth/drive']
# Redirect URI for installed apps, can be left as is
REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob"
# Google Drive Folder mimeType
G_DRIVE_DIR_MIME_TYPE = "application/vnd.google-apps.folder"


class GoogleDrive:
    def __init__(self, token, workdir=None):
        self.__SERVICE_ACCOUNT_INDEX = 0
        self.__token = token
        self.__service = self.authorize(self.__token)
        self.__USE_SERVICE_ACCOUNTS = False
        self._file_uploaded_bytes = 0
        self.uploaded_bytes = 0
        self.start_time = 0
        self.total_time = 0
        self.parent_id = extractId(workdir) if workdir else "root"
        self.status = None
        self.updater = None


    def __upload_empty_file(self, path, file_name, mime_type, parent_id=None):
        media_body = MediaFileUpload(path,
                                     mimetype=mime_type,
                                     resumable=False)
        file_metadata = {
            'name': file_name,
            'description': 'uploaded by gdnan',
            'mimeType': mime_type,
        }
        if parent_id is not None:
            file_metadata['parents'] = [parent_id]
        return self.__service.files().create(supportsTeamDrives=True,
                                             body=file_metadata, media_body=media_body).execute()

    def switchServiceAccount(self):
        service_account_count = len(os.listdir(self.__token))
        if self.__SERVICE_ACCOUNT_INDEX == service_account_count - 1:
            self.__SERVICE_ACCOUNT_INDEX = 0
        self.__SERVICE_ACCOUNT_INDEX += 1
        LOGGER.info(f"Switching to {self.__SERVICE_ACCOUNT_INDEX}.json service account")
        self.__service = self.authorize(self.__token)

    @retry(wait=wait_exponential(multiplier=2, min=3, max=6), stop=stop_after_attempt(5),
           retry=retry_if_exception_type(HttpError), before=before_log(LOGGER, logging.DEBUG))
    def make_public(self, drive_id):
        permissions = {
            'role': 'reader',
            'type': 'anyone',
            'value': None,
            'withLink': True
        }
        try:
            return self.__service.permissions().create(supportsTeamDrives=True, fileId=drive_id, body=permissions).execute()
        except HttpError as err:
            if err.resp.get('content-type', '').startswith('application/json'):
                reason = json.loads(err.content).get('error').get('errors')[0].get('reason')
                if reason == 'rateLimitExceeded':
                    raise err
                else:
                    message = json.loads(err.content).get('error').get('errors')[0].get('message')
                    raise GoogleDriveError(message) from None


    @retry(wait=wait_exponential(multiplier=2, min=3, max=6), stop=stop_after_attempt(5),
           retry=retry_if_exception_type(HttpError), before=before_log(LOGGER, logging.DEBUG))
    def upload_file(self, file_path, file_name, mime_type, parent_id):
        # File body description
        file_metadata = {
            'name': file_name,
            'description': 'uploaded by gdnan',
            'mimeType': mime_type,
        }
        if parent_id is not None:
            file_metadata['parents'] = [parent_id]

        if os.path.getsize(file_path) == 0:
            media_body = MediaFileUpload(file_path,
                                         mimetype=mime_type,
                                         resumable=False)
            response = self.__service.files().create(supportsTeamDrives=True,
                                                     body=file_metadata, media_body=media_body).execute()
            drive_file = self.__service.files().get(supportsTeamDrives=True,
                                                    fileId=response['id']).execute()
            return drive_file
        media_body = MediaFileUpload(file_path,
                                     mimetype=mime_type,
                                     resumable=True,
                                     chunksize=50 * 1024 * 1024)

        # Insert a file
        drive_file = self.__service.files().create(supportsTeamDrives=True,
                                                   body=file_metadata, media_body=media_body)
        response = None
        while response is None:
            try:
                self.status, response = drive_file.next_chunk()
            except HttpError as err:
                if err.resp.get('content-type', '').startswith('application/json'):
                    reason = json.loads(err.content).get('error').get('errors')[0].get('reason')
                    if reason == 'userRateLimitExceeded' or reason == 'dailyLimitExceeded':
                        if self.__USE_SERVICE_ACCOUNTS:
                            self.switchServiceAccount()
                            LOGGER.info(f"Got: {reason}, Trying Again.")
                            return self.upload_file(file_path, file_name, mime_type, parent_id)
                    elif reason == 'rateLimitExceeded':
                        raise err
                    else:
                        message = json.loads(err.content).get('error').get('errors')[0].get('message')
                        raise GoogleDriveError(message) from None
        self._file_uploaded_bytes = 0
        # Define file instance and get url for download
        drive_file = self.__service.files().get(supportsTeamDrives=True, fileId=response['id']).execute()
        return drive_file


    def upload(self, file_path: str, folder=None):
        if self.__USE_SERVICE_ACCOUNTS:
            self.service_account_count = len(os.listdir(self.__token))
        if folder:
            parent_id = folder
        else:
            parent_id = self.parent_id
        file_name = os.path.basename(file_path)
        LOGGER.info("Uploading File: " + file_path)
        self.start_time = time.time()
        if os.path.isfile(file_path):
            try:
                mime_type = self.get_mime_type(file_path)
                file = self.upload_file(file_path, file_name, mime_type, parent_id)
                if file is None:
                    raise Exception('Upload has been manually cancelled')
                file = GoogleDriveFile(file)
                LOGGER.info("Uploaded To G-Drive: " + file_path)
            except Exception as e:
                if isinstance(e, RetryError):
                    LOGGER.info(f"Total Attempts: {e.last_attempt.attempt_number}")
                    err = e.last_attempt.exception()
                else:
                    err = e
                raise GoogleDriveError(err) from None
                return
        elif os.path.isdir(file_path):
            try:
                file = self.create_folder(os.path.basename(os.path.abspath(file_name)), parent_id)
                result = self.upload_dir(file_path, file.id)
                if result is None:
                    raise Exception('Upload has been manually cancelled!')
                LOGGER.info("Uploaded To G-Drive: " + file_name)
            except Exception as e:
                if isinstance(e, RetryError):
                    LOGGER.info(f"Total Attempts: {e.last_attempt.attempt_number}")
                    err = e.last_attempt.exception()
                else:
                    err = e
                raise GoogleDriveError(err) from None
                return
        else:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), file_path)
        return file

    @retry(wait=wait_exponential(multiplier=2, min=3, max=6), stop=stop_after_attempt(5),
           retry=retry_if_exception_type(HttpError), before=before_log(LOGGER, logging.DEBUG))
    def copyFile(self, file_id, dest_id):
        body = {
            'parents': [dest_id]
        }

        try:
            res = self.__service.files().copy(supportsAllDrives=True,fileId=file_id,body=body).execute()
            return res
        except HttpError as err:
            if err.resp.get('content-type', '').startswith('application/json'):
                reason = json.loads(err.content).get('error').get('errors')[0].get('reason')
                if reason == 'userRateLimitExceeded' or reason == 'dailyLimitExceeded':
                    if self.__USE_SERVICE_ACCOUNTS:
                        self.switchServiceAccount()
                        LOGGER.info(f"Got: {reason}, Trying Again.")
                        return self.copyFile(file_id,dest_id)
                else:
                    raise err

    @retry(wait=wait_exponential(multiplier=2, min=3, max=6), stop=stop_after_attempt(5),
           retry=retry_if_exception_type(HttpError), before=before_log(LOGGER, logging.DEBUG))
    def getFile(self,file_id):
        try:
            return self.__service.files().get(supportsAllDrives=True, fileId=file_id,
                                              fields="name,id,mimeType,size,parents").execute()
        except HttpError as err:
            if err.resp.get('content-type', '').startswith('application/json'):
                reason = json.loads(err.content).get('error').get('errors')[0].get('reason')
                if reason == 'rateLimitExceeded':
                    raise err
                else:
                    message = json.loads(err.content).get('error').get('errors')[0].get('message')
                    raise GoogleDriveError(message) from None


    @retry(wait=wait_exponential(multiplier=2, min=3, max=6), stop=stop_after_attempt(5),
           retry=retry_if_exception_type(HttpError), before=before_log(LOGGER, logging.DEBUG))
    def getFilesByFolderId(self,folder_id):
        page_token = None
        q = f"'{folder_id}' in parents"
        files = []
        while True:
            response = self.__service.files().list(supportsTeamDrives=True,
                                                   includeTeamDriveItems=True,
                                                   q=q,
                                                   spaces='drive',
                                                   pageSize=200,
                                                   fields='nextPageToken, files(id, name, mimeType,size)',
                                                   pageToken=page_token).execute()
            for file in response.get('files', []):
                files.append(file)
            page_token = response.get('nextPageToken', None)
            if page_token is None:
                break
        return files

    def clone(self, file_id: str, folder=None):
        self.transferred_size = 0
        if folder:
            parent_id = folder
        else:
            parent_id = self.parent_id
        if file_id == parent_id:
            raise GoogleDriveError("Can't clone the working directory in itself.")
        LOGGER.info(f"File ID: {file_id}")
        try:
            meta = self.getFile(file_id)
            if meta.get("mimeType") == G_DRIVE_DIR_MIME_TYPE:
                file = self.create_folder(meta.get('name'), parent_id)
                result = self.cloneFolder(meta.get('name'), meta.get('name'), meta.get('id'), file.id)
                file.size = int(self.transferred_size)
            else:
                file = self.copyFile(meta.get('id'), parent_id)
                file = GoogleDriveFile(file)
                file.size = int(meta.get('size'))
        except Exception as err:
            if isinstance(err, RetryError):
                LOGGER.info(f"Total Attempts: {err.last_attempt.attempt_number}")
                err = err.last_attempt.exception()
            err = str(err).replace('>', '').replace('<', '')
            raise GoogleDriveError(err) from None
        return file

    def cloneFolder(self, name, local_path, folder_id, parent_id):
        LOGGER.info(f"Syncing: {local_path}")
        files = self.getFilesByFolderId(folder_id)
        new_id = None
        if len(files) == 0:
            return parent_id
        for file in files:
            if file.get('mimeType') == G_DRIVE_DIR_MIME_TYPE:
                file_path = os.path.join(local_path, file.get('name'))
                current_dir = self.create_folder(file.get('name'), parent_id)
                new_id = self.cloneFolder(file.get('name'), file_path, file.get('id'), current_dir.id)
            else:
                try:
                    self.transferred_size += int(file.get('size'))
                except TypeError:
                    pass
                try:
                    self.copyFile(file.get('id'), parent_id)
                    new_id = parent_id
                except Exception as e:
                    if isinstance(e, RetryError):
                        LOGGER.info(f"Total Attempts: {e.last_attempt.attempt_number}")
                        err = e.last_attempt.exception()
                    else:
                        err = e
                    LOGGER.error(err)
        return new_id

    @retry(wait=wait_exponential(multiplier=2, min=3, max=6), stop=stop_after_attempt(5),
           retry=retry_if_exception_type(HttpError), before=before_log(LOGGER, logging.DEBUG))
    def create_folder(self, directory_name, parent_id):
        file_metadata = {
            "name": directory_name,
            "mimeType": G_DRIVE_DIR_MIME_TYPE
        }
        if parent_id is not None:
            file_metadata["parents"] = [parent_id]
        try:
            file = self.__service.files().create(supportsTeamDrives=True, body=file_metadata).execute()
        except HttpError as err:
            if err.resp.get('content-type', '').startswith('application/json'):
                reason = json.loads(err.content).get('error').get('errors')[0].get('reason')
                if reason == 'rateLimitExceeded':
                    raise err
                else:
                    message = json.loads(err.content).get('error').get('errors')[0].get('message')
                    raise GoogleDriveError(message) from None
        LOGGER.info("Created Google-Drive Folder:\nName: {}".format(file.get("name")))
        return GoogleDriveFile(file)

    def upload_dir(self, input_directory, parent_id):
        list_dirs = os.listdir(input_directory)
        if len(list_dirs) == 0:
            return parent_id
        new_id = None
        for item in list_dirs:
            current_file_name = os.path.join(input_directory, item)
            if os.path.isdir(current_file_name):
                current_dir = self.create_folder(item, parent_id)
                new_id = self.upload_dir(current_file_name, current_dir.id)
            else:
                mime_type = self.get_mime_type(current_file_name)
                file_name = current_file_name.split("/")[-1]
                # current_file_name will have the full path
                self.upload_file(current_file_name, file_name, mime_type, parent_id)
                new_id = parent_id
        return new_id

    def authorize(self, token):
        credentials = None
        if isinstance(token, OAuth2Credentials):
            credentials = token
        elif os.path.exists(token):
            if os.path.isfile(token) and token.endswith(".pickle"):
                with open(token, 'rb') as f:
                    credentials = pickle.load(f)
                if credentials is None or credentials.invalid:
                    if credentials and credentials.refresh_token:
                        creds.refresh(Http())
                    else:
                        raise GoogleDriveError("InvalidCredentials: Invalid credentials provided.")
                # Save the credentials for the next run
                with open(token, 'wb') as token:
                    pickle.dump(credentials, token)
            else:
                status = parse_service_accounts(token)
                if status:
                    credentials = service_account.Credentials.from_service_account_file(
                        f'{token}/{self.__SERVICE_ACCOUNT_INDEX}.json',
                        scopes=OAUTH_SCOPE)
                    self.__USE_SERVICE_ACCOUNTS = True
        else:
            raise GoogleDriveError("InvalidCredentials: Invalid credentials provided.")
        return build('drive', 'v3', credentials=credentials, cache_discovery=False)

    def escapes(self, str):
        chars = ['\\', "'", '"', r'\a', r'\b', r'\f', r'\n', r'\r', r'\t']
        for char in chars:
            str = str.replace(char, '\\'+char)
        return str

    def get_mime_type(self, file_path):
        mime_type = guess_type(file_path)
        return mime_type if mime_type[0] else "text/plain"


    def search(self, fileName, folder=None, limit=20, next_page_token=None):
        files = []
        fileName = self.escapes(str(fileName))
        # Create Search Query for API request.
        query = f"(name contains '{fileName}')"
        if folder:
          query += f"and '{folder}' in parents"
        response = self.__service.files().list(supportsTeamDrives=True,
                                               includeTeamDriveItems=True,
                                               q=query,
                                               spaces='drive',
                                               pageSize=limit,
                                               fields='nextPageToken, files(id, name, mimeType, size)',
                                               orderBy='modifiedTime desc',
                                               pageToken=next_page_token).execute()
        for file in response.get('files', []):
            files.append(GoogleDriveFile(file))
        return files, response.get("nextPageToken")

    @retry(wait=wait_exponential(multiplier=2, min=3, max=6), stop=stop_after_attempt(3),
        retry=retry_if_exception_type(HttpError), before=before_log(LOGGER, logging.DEBUG))
    def delete(self, file_id: str, permanent=False):
        try:
            if permanent:
                response = self.__service.files().delete(fileId=file_id, supportsAllDrives=True).execute()
            else:
                response = self.__service.files().update(fileId=file_id, body={'trashed': True}, supportsAllDrives=True).execute()
            return response
        except HttpError as err:
            if err.resp.get('content-type', '').startswith('application/json'):
                reason = json.loads(err.content).get('error').get('errors')[0].get('reason')
                if reason == "rateLimitExceeded":
                    raise err
                else:
                    message = json.loads(err.content).get('error').get('errors')[0].get('message')
                    raise GoogleDriveError(message) from None

    @retry(wait=wait_exponential(multiplier=2, min=3, max=6), stop=stop_after_attempt(3),
        retry=retry_if_exception_type(HttpError), before=before_log(LOGGER, logging.DEBUG))
    def emptyTrash(self):
        try:
            return self.__service.files().emptyTrash().execute()
        except HttpError as err:
            if err.resp.get('content-type', '').startswith('application/json'):
                reason = json.loads(err.content).get('error').get('errors')[0].get('reason')
                if reason == "rateLimitExceeded":
                    raise err
                else:
                    message = json.loads(err.content).get('error').get('errors')[0].get('message')
                    raise GoogleDriveError(message) from None

    @retry(wait=wait_exponential(multiplier=2, min=3, max=6), stop=stop_after_attempt(3),
        retry=retry_if_exception_type(HttpError), before=before_log(LOGGER, logging.DEBUG))
    def move(self, file_id, folder=False):
        if not folder:
            folder = self.parent_id
        file = self.getFile(file_id)
        previous_parents = ",".join(file.get('parents'))
        try:
            file = self.__service.files().update(
                fileId=file_id,
                addParents=folder,
                removeParents=previous_parents,
                fields='id,name,size,mimeType,parents',
                supportsAllDrives=True,
            ).execute()
        except HttpError as err:
            if err.resp.get('content-type', '').startswith('application/json'):
                reason = json.loads(err.content).get('error').get('errors')[0].get('reason')
                if reason == "rateLimitExceeded":
                    raise err
                else:
                    message = json.loads(err.content).get('error').get('errors')[0].get('message')
                    raise GoogleDriveError(message) from None
        return GoogleDriveFile(file)



class GoogleDriveFile:
    def __init__(self, file):
        self.id = file.get('id')
        self.name = file.get('name')
        self.mimeType = file.get('mimeType')
        self.size = file.get('size')
        self.driveId = file.get('driveId')
        self.teamDriveId = file.get('teamDriveId')
        self.kind = file.get('kind')
        self.url = create_link(self.id, self.mimeType)

class Auth:
    def __init__(self, GooogleDriveClientID, GooogleDriveClientSecret):
        self.__flow = OAuth2WebServerFlow(
              GooogleDriveClientID,
              GooogleDriveClientSecret,
              OAUTH_SCOPE,
              redirect_uri=REDIRECT_URI
        )

    def get_url(self):
        return self.__flow.step1_get_authorize_url()

    def exchange_code(self, code, save=False):
        try:
            credentials = self.__flow.step2_exchange(code)
            if save:
                with open(save, "wb") as f:
                    pickle.dump(credentials, f)
                return save
            return credentials
        except FlowExchangeError as err:
            raise GoogleDriveError("Invalid Authorization Code Provided !") from None


class GoogleDriveError(Exception):
    def __init__(self, m):
        self.message = m
    def __str__(self):
        return self.message.replace("<","").replace(">","")

def create_link(id, mimeType):
    if mimeType == G_DRIVE_DIR_MIME_TYPE:
        return "https://drive.google.com/drive/folders/{}".format(id)
    else:
        return "https://drive.google.com/uc?id={}&export=download".format(id)

def extractId(link: str):
    if "folders" in link or "file" in link:
        regex = r"https://drive\.google\.com/(drive)?/?u?/?\d?/?(mobile)?/?(file)?(folders)?/?d?/([-\w]+)[?+]?/?(w+)?"
        res = re.search(regex,link)
        if res is None:
            raise IndexError("GDrive ID not found.")
        return res.group(5)
    if len(link) == 33 or len(link) == 19 and not "/" in link:
        return link
    parsed = urlparse.urlparse(link)
    return parse_qs(parsed.query)['id'][0]

def parse_service_accounts(token: str):
    if os.path.exists(os.path.join(token, "0.json")):
        return True
    else:
        listdir = os.listdir(token)
        if len(listdir) != 0:
            i = 0
            for file in listdir:
                if file.lower().endswith(".json"):
                    os.rename(os.path.join(token,file), os.path.join(token, f"{i}.json"))
                    i += 1
                else:
                    LOGGER.warning(f"An unknown file - {file} exists in service accounts directory remove it unless code will break.")
            if i != 0:
                return True
            else:
                raise FileNotFoundError("No service accounts found in the directory.")
        else:
            raise FileNotFoundError("No file exists in service account's directory.")