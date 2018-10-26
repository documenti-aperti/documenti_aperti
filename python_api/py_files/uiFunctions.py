
import os 																# Low level library to work with directories
from git 				import Repo 									# to work with gitea's repositories
from internetarchive 	import upload as iaUpload						# to upload files on archive.org
from shutil 			import unpack_archive, rmtree					# high level library to work on directories
from requests 			import get as httpGet 							# to make http GET requests
from traceback 			import print_exc								# to handle exceptions and print traceback

def HOCR(idRepo, uid, hocrData, db):
	"""
	:param idRepo: repo's id
	:param uid: id of the user that requested the action
	:param hocrData: new HOCR data
	:param db: database to use for getting information
	:type idRepo: int
	:type uid: int
	:type hocrData: str
	:type db: pymysql.connections.Connection

	note:: This function is called whenever an user wants to save an edited HOCR file using the proofreader inside the website
	"""

	# Create temporary folder name
	tempFolder = "tempGit" + str(sum([1 for i in os.listdir() if i.find("tempGit") != -1]))

	# Error Handling
	try:
		# Getting repository's information
		repoInfos = db.getRepoInfos(idRepo)
		name = repoInfos[0]

		# Cloning repository
		repo = Repo.clone_from("https://documentiaperti.org/" + repoInfos[2] + "/" + repoInfos[0] + ".git", tempFolder, depth=1)

		# Writing new HOCR file
		with open(os.path.join(tempFolder, "hocr" , name + ".hocr"), "w") as newFileHOCR:
			newFileHOCR.write(hocrData)

		# Using hocr-tools for splitting a single HOCR file in more files by the number of pages
		# 	This has to be done because of the next tool "hocr-pdf"
		os.system("hocr-split " + os.path.join(tempFolder, "hocr", name + ".hocr") + " '" + os.path.join(tempFolder, "images", "%d.hocr") + "'")

		# hocr-pdf, which is a part of hocr-tools, is required for creating a PDF file that contains the saved text from the new hocr file
		# 	The hocr pages need to be splitted in hocr files because hocr-pdf takes all the images and HOCRs from a single folder (/images) and
		#	searching for every HOCR file it's relative image named as the HOCR file and using the name for sorting them in the correct way
		os.system("hocr-pdf --savefile " + os.path.join(tempFolder ,"pdf_complete", name + ".pdf") + " " + os.path.join(tempFolder, "images"))

		# Removing splitted HOCR files used for hocr-pdf 
		for file in [i for i in os.listdir(os.path.join(tempFolder, "images")) if i.endswith(".hocr")]:
			os.remove(os.path.join(tempFolder, "images", file))

		# Adding changes to repository
		repo.git.add(A=True)

		# Getting information about repository and Gitea for pushing it
		admin = db.getAdmin()
		repoInfos = db.getRepoInfos(idRepo)
		nameApplicant = db.getUserName(uid)

		# Add admin to repo's collaboration
		db.addCollaboration(idRepo, admin[0], 2)

		# Creating a new commit
		repo.git.commit("-m", "Modifica HOCR richiesta da @" + nameApplicant)

		# Replacing the remote origin because the actual one is invalid
		repo.delete_remote("origin")
		origin = repo.create_remote("origin", url="https://" + admin[1] + ":" + admin[2] + "@documentiaperti.org/" + repoInfos[2] + "/" + repoInfos[0] + ".git")

		# Pushing the new repository on Gitea
		origin.push(refspec='{}:{}'.format("master", "master"))

		#Closing repository
		repo.close()

	except:
		#Error handling with traceback print
		print_exc()

	# Deleting tempFolder if it exists
	if os.path.exists(tempFolder): rmtree(tempFolder)

def uploadPDFOnArchive(idRepo, uid, linkZip, db):
	"""
	:param idRepo: repo's id
	:param uid: id of the user that requested the action
	:param linkZip: location of zip file to be downloaded
	:param db: database to use for getting information
	:type idRepo: int
	:type uid: int
	:type linkZip: str
	:type db: pymysql.connections.Connection

	note:: This function is called whenever an user wants to upload a PDF from a repo's release to archive.org
	"""

	# Create temporary folder name
	tempFolder = "tempGit" + str(sum([1 for i in os.listdir() if i.find("tempGit") != -1]))

	# Creating a cursor for getting information about archive.org accounts
	cursor = db.getCursor()

	# Getting information about repository
	repoInfos = db.getRepoInfos(idRepo)

	# Error Handling
	try:
		# Creating temporary folder
		os.mkdir(tempFolder)

		# Adding zip file downloaded from web
		with open(os.path.join(tempFolder, repoInfos[0] + ".zip"), "wb") as zipFile:
			zipFile.write(httpGet(linkZip).content)

		# Unzipping archive
		unpack_archive(os.path.join(tempFolder, repoInfos[0] + ".zip"), extract_dir=tempFolder)

		# Getting archive.org user's data
		cursor.execute("SELECT s3access,s3key FROM gitea.archiveorg WHERE uid=%s", (uid,))
		s3Data = cursor.fetchone()

		# Error handling for iaUpload
		# 	This is done because sometimes uploading on archive.org can return an error (i.e. document already exists)
		try:
			# Document's metadata for archive.org
			md = dict(title=repoInfos[0],mediatype='texts', description='Document uploaded from documentiaperti.org',collection="test_collection")
			# Uploading on archive.org
			r = iaUpload(repoInfos[0] + "_" + db.getUserName(uid), files=[os.path.join(tempFolder, repoInfos[0], "pdf_complete", repoInfos[0] + ".pdf")], access_key=s3Data[0], secret_key=s3Data[1],metadata=md)
		except:
			#Error handling with traceback print
			print_exc()
	except:
		#Error handling with traceback print
		print_exc()

	if os.path.exists(tempFolder): rmtree(tempFolder)