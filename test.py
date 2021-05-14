# Importing Module
from gdnan import GoogleDrive, Auth, extractId, create_link

# Client ID & Secret Obtained from Google Developer Console

# ⚠️ Change this before testing.
GooogleDriveClientID = "580378293805-5bf0kn9vw10wj54ld0nki9s0ogddmo1b5s.apps.googleusercontent.com"
GooogleDriveClientSecret = "XQhhKbiGCNg28ehTLa5OJG1wXC"


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
#auth.exchange_code(received_code, "token.pickle")


# Now after generating .pickle or credentials you need to use only below steps
# Authorized via credentials
gd = GoogleDrive(credentials)
# Or You can Authorize via .pickle file too
# and can set the working directory, like for share drive.
#workdir_id = extractId("https://drive.google.com/folderview?id=1Aricl6VpSiMmgFkgUSeTXiQh7WYxW6np")
                                 #optional
#gd = GoogleDrive("token.pickle", workdir_id)

# Upload file from local storage
uploaded_file = gd.upload("README.md")
print(uploaded_file.name)
#>> example.txt

# To get Google Drive url
print(uploaded_file.url)
#>> https://drive.google.com/uc?id=10xN4KBjKJXUwIHUv1R5rihbthYuENMUB&export=download
# Alternate way
print(create_link(uploaded_file.id, uploaded_file.mimeType))
#>> https://drive.google.com/uc?id=10xN4KBjKJXUwIHUv1R5rihbthYuENMUB&export=download

# To create a folder named "Hello World !"
folder = gd.create_folder("Hello World!", workdir_id)
print(folder.name)
#>> Hello World!

# Clone/Copy file or folder
cloned_file = gd.clone(uploaded_file.id)
print(cloned_file.name)
#>> example.txt

# Move file from one folder to another
gd.move(cloned_file.id, folder.id)

# Make files public or set permission for the file to publically viewable
gd.make_public(cloned_file.id)

# Search for the file       #optional    #optional
files, _ = gd.search(uploaded_file.name, limit=2, parent=workdir_id)
for file in files:
    print(file.name)
#>> example.txt

# Move file to trash
gd.delete(uploaded_file.id)
# Delete file permanently
gd.delete(folder.id, True)


# Empty Trash of the users account
gd.emptyTrash()