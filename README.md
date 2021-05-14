# gdnan
A Google Drive API wrapper written in python by [@viperadnan](https://viperadnan-git.github.io) with ♥️.

## Project's Base
The base of the project taken from lzzy12's repo python-aria-mirror-bot and modified, improved and compiled in a pip package.

### Installing
Install using pip
```sh
pip3 install gdnan
```

### Usage
```py
# Importing Modules
from gdnan import GoogleDrive, Auth, extractId, create_link

# Client ID & Secret Obtained from Google Developer Console
GooogleDriveClientID = "9999199991-128shwbnwinpcqv6hn7b29wuww4gmji.apps.googleusercontent.com"
GooogleDriveClientSecret = "2lhkFmsQ0W7wJaua72HwodjZ"


# The below method is only for one time, you cam use saved 
# credentials for later use.
# Call the Auth module 
auth = Auth(GooogleDriveClientID, GooogleDriveClientSecret)

# Get the Authorization URL
print("Open this url in browser and enter the received code")
print(auth.get_url())
received_code = input("Enter received code: ")

# Exchange received code and get credentials
# You can store the credentials wherever you want
credentials = auth.exchange_code(received_code)
# Or save it in token.pickle or any other file
                                    #optional
auth.exchange_code(received_code, "token.pickle")


# Now after generating .pickle or credentials you need to use only below steps
# Authorized via credentials
gd = GoogleDrive(credentials)
# Or You can Authorize via .pickle file too
# and can set the working directory, like for share drive.
workdir_id = extractId("https://drive.google.com/folderview?id=1Aricl6VpSiMmgFkgUSeTXiQh7WYxW6np")
                                 #optional
gd = GoogleDrive("token.pickle", workdir_id)

# Upload file from local storage
uploaded_file = gd.upload("path/to/file/or/folder/example.txt")
# Upload file to custom folder using folder's id               #Optional
uploaded_file = gd.upload("path/to/file/or/folder/example.txt", "root")
print(uploaded_file.name)
>> example.txt

# To get Google Drive url
print(uploaded_file.url)
>> https://drive.google.com/uc?id=10xN4KBjKJXUwIHUv1R5rihbthYuENMUB&export=download
# Alternate way
print(create_link(uploaded_file.id, uploaded_file.mimeType))
>> https://drive.google.com/uc?id=10xN4KBjKJXUwIHUv1R5rihbthYuENMUB&export=download

# To create a folder named "Hello World !"
#                           # Name       # Parent ID
folder = gd.create_folder("Hello World!", workdir_id)
print(folder.name)
>> Hello World!

# Clone/Copy file or folder, you can specify custom folder id by "folder" parameter
cloned_file = gd.clone(uploaded_file.id)
print(cloned_file.name)
>> example.txt

# Move file from one folder to another
gd.move(cloned_file.id, folder.id)

# Make files public or set permission for the file to publically viewable
gd.make_public(cloned_file.id)

# Search for the file       #optional    #optional
files, next_page_token = gd.search(uploaded_file.name, limit=2, folder=workdir_id)
for file in files:
    print(file.name)
>> example.txt

# Move file to trash
gd.delete(uploaded_file.id)
# Delete file permanently
gd.delete(folder.id, True)

# Empty Trash of the users account
gd.emptyTrash()
```

#### Using Service Accounts
If you want to use service accounts than put a copy of all of your service accounts in a folder and use code below
```py
from gdnan import GoogleDrive
gd = GoogleDrive("path/to/service/account/folder", workdir_id)
```
this will automatically rename your service accounts to `0.json 1.json 2.json...` (if not renamed) and automatically switch between service accounts if daily quota exceeded.

#### Testing
Test code by running [test.py](./test.py) in your terminal with `python3 test.py`, don't forget to change the GooogleDriveClientID and GooogleDriveClientSecret.

### Copyright & License
- Copyright &copy; 2021 &mdash; [Adnan Ahmad](https://github.com/viperadnan-git)
- Licensed under the terms of the [GNU General Public License Version 3 &dash; 29 June 2007](./LICENSE)