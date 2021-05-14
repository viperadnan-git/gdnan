import setuptools

with open('requirements.txt') as f:
    requirements = f.read().splitlines()

with open("README.md", "r") as f:
    long_description = f.read()

setuptools.setup(
    name="gdnan",
    version="1.0.0",
    author="Adnan Ahmad",
    author_email="viperadnan@gmail.com",
    description="Google Drive API wrapper written in python 3.",
    url = 'https://github.com/viperadnan-git/gdnan',
    download_url = 'https://github.com/viperadnan-git/gdnan/archive/v1.0.0.tar.gz',
    keywords = ['GoogleDrive', 'GoogleDriveAPI', 'GDriveAPI', 'Google', 'Drive', 'Wrapper', 'GDrive'],
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.9",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Operating System :: OS Independent"
    ],
    python_requires='>=3.6',
    py_modules=["gdnan"],
    package_dir={'':'src'},
    install_requires=requirements
)