import os 																# Low level library to work with directories
import json																# Library to elaborate JSON texts
import pySIC 															# Our main library to elaborate image
import re 																# to parse string data
from PyPDF2 			import PdfFileWriter, PdfFileReader 			# to work with pdf files
from traceback 			import print_exc								# to handle exceptions and print traceback
from shutil 			import copy2, rmtree							# high level library to work on directories
from bs4 				import BeautifulSoup 							# to parse HTML files
from git 				import Repo 									# to work with gitea's repositories

def cropAndOCR(idRepo, uid, language, db, debug = False):
	"""
	:param idRepo: repo's id
	:param uid: id of the user that requested the action
	:param language: language to be used for OCR
	:param db: database to use for getting information
	:type idRepo: int
	:type uid: int
	:type language: str
	:type db: pymysql.connections.Connection

	note:: This function is called whenever an user wants to:
			- elaborate new images in raw_data folder
			- change the order of a image in the entire document with it's HOCR file and PDF page
			- delete an image from document with it's HOCR file and PDF page
	"""

	# Create temporary folder name
	tempFolder = "tempGit" + str(sum([1 for i in os.listdir() if i.find("tempGit") != -1]))

	# List of useful directories
	dirOrig = [os.path.join("output", "out_cropper"), "output", os.path.join("output", "out_hocr")]

	# Error handling
	try:
		# Get repository infos
		repoInfos = db.getRepoInfos(idRepo)
		repoName = repoInfos[0]
		repo = Repo.clone_from("https://documentiaperti.org/" + repoInfos[2] + "/" + repoInfos[0] + ".git", tempFolder, depth=1)

		# repos' directories list
		directories = [os.path.join(tempFolder, "raw_data"), os.path.join(tempFolder, "images"), os.path.join(tempFolder, "pdf_complete"), os.path.join(tempFolder, "hocr")]

		# Creating the directory tree
		for direc in directories:
			os.makedirs(direc, exist_ok=True)

		# A dictionary which contains orders
		dataElaboration = {"actualOrder":[], "customOrder":[], "deleteFiles":[]}

		# Check existance and load it
		if os.path.isfile(os.path.join(tempFolder, "raw_data", ".startFrom")):
			with open(os.path.join(tempFolder, "raw_data", ".startFrom"), "r") as startFromFile:
				dataElaboration = json.loads(startFromFile.read())

		# IMAGES
		#   └───delete requested files
		#Delete human selected files from raw_data folder and current ordering
		for c, file in enumerate(dataElaboration["deleteFiles"]):
			ind = (dataElaboration["actualOrder"].index(file) if file in dataElaboration["actualOrder"] else -1, file)
			dataElaboration["deleteFiles"][c] = ind
			os.remove(os.path.join(directories[0], file))
			if ind[0] != -1:
				dataElaboration["actualOrder"][ind[0]] = None

		#Load a list filtered
		dataElaboration["customOrder"] += [i for i in dataElaboration["actualOrder"] if not i in dataElaboration["deleteFiles"] and not i in dataElaboration["customOrder"]] 
		unsortedData = sorted([d for d in os.listdir(os.path.join(tempFolder, "raw_data")) if all([d not in v for v in dataElaboration.values()]) and d != ".startFrom"], key=lambda key: [ int(c) if c.isdigit() else c for c in re.split('([0-9]+)', key) ] )
		addedImages = [image for image in dataElaboration["customOrder"] if not image in dataElaboration["actualOrder"]] + unsortedData
		dataElaboration["customOrder"] += unsortedData
		dataElaboration["customOrder"] = [im for im in dataElaboration["customOrder"] if im != None]

		if debug: print(dataElaboration, addedImages)

		if not dataElaboration["customOrder"]:
			removeAll(idRepo, repoInfos[1], tempFolder, repo, db)
			return

		#Update order file
		with open(os.path.join(tempFolder, "raw_data", ".startFrom"), "w") as startFromFile:
			startFromFile.write(json.dumps({"actualOrder":dataElaboration["customOrder"],"customOrder":[],"deleteFiles":[]}))

		

		#If the user added unelaborated images, then elaborate them
		if addedImages:
			#Copying them into a folder where the pySIC library operate
			for c, file in enumerate(addedImages, 1):
				copy2(os.path.join(tempFolder, "raw_data", file), os.path.join("data", str(c) + "." + file.split(".")[-1].lower()))
			pySIC.elaborate(repoName, ocr=True, lang=language)

			#If unelaborated images are more then 1, merge Hocr files into a new one "0.hocr"
			r_hocr = "1.hocr"
			if len(addedImages) > 1:
				r_hocr = "0.hocr"
				os.system("hocr-combine " + " ".join([os.path.join(dirOrig[-1], i) for i in os.listdir(dirOrig[-1])]) + " > " + os.path.join(dirOrig[-1], "0.hocr"))

			#Open elaborated hocr file, change his previous header with a new one that can be handled by Hocr-proofreader
			with open(os.path.join(dirOrig[-1], r_hocr), "r") as f:
				tempHocr = f.read()
			tempHocr = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">\n<html>\n' + "\n".join(tempHocr.split("\n")[3:])
			tempHocr = re.sub(r"title=([\"'])image (&quot;)*[\"']*(\/[\w.]*)*\/(\w*.\w*)(&quot;)*[\"']*", r'title=\1image \4;scan_res 300 300', tempHocr)
			
			#Clean hocr files' folder
			rmtree(dirOrig[-1])
			os.mkdir(dirOrig[-1])

		# IMAGES
		#   └───sorting of both old and new images
		#		   └───create a temporary directory which contains elaborated images in correct order
		os.makedirs("tempData", exist_ok=True)

		#		   └───sorting and adding
		for i, file in enumerate(dataElaboration["customOrder"], 1):
			#check if the file was elaborated before
			if file in addedImages:
				final_dir = dirOrig[0]
				final_i = addedImages.index(file)

			#the image has been elaborated before
			else:
				final_dir = directories[1]
				final_i = dataElaboration["actualOrder"].index(file)

			#Adding it
			os.rename(os.path.join(final_dir, str(final_i + 1) + ".jpg"), os.path.join("tempData", str(i) + ".jpg"))

		#	└───Moving files from temp folder to Repos folder
		rmtree(directories[1])
		os.makedirs(directories[1], exist_ok=True)
		for file in os.listdir("tempData"):
			os.rename(os.path.join("tempData", file), os.path.join(directories[1], file))
		rmtree("tempData")

		#PDF
		#	└───Final Pdf
		outputPdf = PdfFileWriter()

		#	└───Newest Pdf
		if addedImages:
			file_temp = open(os.path.join(dirOrig[1], repoName + ".pdf"), "rb")
			tempPdf = PdfFileReader(file_temp)

		#	└───Older Pdf
		if os.listdir(directories[2]):
			file_main = open(os.path.join(directories[2], repoName + ".pdf"), "rb")
			mainPdf = PdfFileReader(file_main)

		#	└───Adding pages to final pdf
		for file in dataElaboration["customOrder"]:
			#check if the file was elaborated before
			if file in addedImages:
				outputPdf.addPage(tempPdf.getPage(addedImages.index(file)))

			#the image has been elaborated before
			else:
				outputPdf.addPage(mainPdf.getPage(dataElaboration["actualOrder"].index(file)))

		#	└───Saving datas
		with open(os.path.join(directories[2], repoName + "?.pdf"), "wb") as outputStream:
			outputPdf.write(outputStream)

		#close
		if "file_temp" in locals().keys():
			file_temp.close()
		if "file_main" in locals().keys():
			file_main.close()

		#Rename it to override
		os.rename(os.path.join(directories[2], repoName + "?.pdf"), os.path.join(directories[2], repoName + ".pdf"))

		#HOCR
		#	└───Divide elaborated hocr in pages identified by the image index
		if addedImages :
			#Create a structure to manage hocr
			tempHocr = BeautifulSoup(tempHocr, "html.parser")
			outputHocr = tempHocr

			#Creates a list of couples (image index, a slice of the html code rapresenting the page) with regular expression
			tempHocr = [(int(re.search(r"image [\"']*(&quot)*(\d*)\.\w*[\"']*(&quot)*", str(page)).group(2)), page) for page in tempHocr.findAll("div", {"class": "ocr_page"})]

			#And sort it
			tempHocr.sort(key=lambda tuple:tuple[0])

		#	└───Divide unelaborated hocr in pages identified by the image index
		if os.listdir(directories[3]) :
			#Create a structure to manage hocr
			with open(os.path.join(directories[3], repoName + ".hocr"), "r") as hocrF:
				mainHocr = BeautifulSoup(hocrF.read(), "html.parser")
			outputHocr = mainHocr

			#Creates a list of couples (image index, a slice of the html code rapresenting the page) with regular expression
			mainHocr = [(int(re.search(r"image [\"']*(&quot)*(\d*)\.\w*[\"']*(&quot)*", str(page)).group(2)), page) for page in mainHocr.findAll("div", {"class": "ocr_page"})]

			#And sort it
			mainHocr.sort(key=lambda tuple:tuple[0])

		#Get an empty html file with header
		outputHocr.body.clear()

		#Create a regular expressions parser
		parser = re.compile(r"image [0-9]*\.[a-zA-Z]*")

		#Order hocr pages following order given by user
		for i, file in enumerate(dataElaboration["customOrder"], 1):
			#Check where the image is located and then add its html piece of code to the final Hocr
			if file in addedImages:
				final_i = addedImages.index(file)
				outputHocr.body.append(BeautifulSoup(parser.sub(r"image %s.jpg" % str(i), str(tempHocr[final_i][1])), "html.parser"))
			else:
				final_i = dataElaboration["actualOrder"].index(file)
				outputHocr.body.append(BeautifulSoup(parser.sub(r"image %s.jpg" % str(i), str(mainHocr[final_i][1])), "html.parser"))


		#Save final hocr
		with open(os.path.join(directories[3],  repoName + ".hocr"), "w") as fileHocrData:
			fileHocrData.write(str(outputHocr))

		#GIT UPLOADING
		#	└───Add edits to commit
		repo.git.add(A=True)

		#	└───Get the required informations about the repository
		# 		[	We already know some of this informations but cause of the long time gap between the	]
		# 		[	submit and this point, informations may be changed.										]
		admin = db.getAdmin()
		repoInfos = db.getRepoInfos(idRepo)
		nameApplicant = db.getUserName(uid)

		#	└───Add Admin to repos' collaboration
		db.addCollaboration(idRepo, admin[0], 2)

		#Commit
		repo.git.commit("-m", "Elaborazione documenti e richiesta da @" + nameApplicant)

		#Create new "origin remote" by replacing it
		repo.delete_remote("origin")
		origin = repo.create_remote("origin", url="https://" + admin[1] + ":" + admin[2] + "@documentiaperti.org/" + repoInfos[2] + "/" + repoInfos[0] + ".git")

		#Pushing the new repository
		origin.push(refspec='{}:{}'.format("master", "master"))

		#Closing repository
		repo.close()

	except Exception as e:
		#Error handling with traceback print
		print_exc()

	#Cleaning elaboration datas
	if os.path.exists(tempFolder): rmtree(tempFolder)
	if os.path.exists("data"): rmtree("data")
	if os.path.exists(dirOrig[0]): rmtree(dirOrig[0])
	if os.path.exists(dirOrig[-1]): rmtree(dirOrig[-1])
	os.mkdir("data")
	os.mkdir(dirOrig[0])
	os.mkdir(dirOrig[-1])

	#Remove pdf from elaboration folder
	if os.path.exists(os.path.join(dirOrig[1], repoName + ".pdf")):
		os.remove(os.path.join(dirOrig[1], repoName + ".pdf"))


def removeAll(idRepo, uid, tempFolder, gitObj, db):
	#Remove all data
	if os.path.exists(os.path.join(tempFolder, "raw_data")): rmtree(os.path.join(tempFolder, "raw_data"))
	if os.path.exists(os.path.join(tempFolder, "images")): rmtree(os.path.join(tempFolder, "images"))
	if os.path.exists(os.path.join(tempFolder, "pdf_complete")): rmtree(os.path.join(tempFolder, "pdf_complete"))
	if os.path.exists(os.path.join(tempFolder, "hocr")): rmtree(os.path.join(tempFolder, "hocr"))

	#GIT UPLOADING
	#	└───Add edits to commit
	gitObj.git.add(A=True)

	#	└───Get the required informations about the repository
	# 		[	We already know some of this informations but cause of the long time gap between the	]
	# 		[	submit and this point, informations may be changed.										]
	admin = db.getAdmin()
	repoInfos = db.getRepoInfos(idRepo)
	nameApplicant = db.getUserName(uid)

	#	└───Add Admin to repos' collaboration
	db.addCollaboration(idRepo, admin[0], 2)

	#Commit
	gitObj.git.commit("-m", "Rimozione completa richiesta da @" + nameApplicant)

	#Create new "origin remote" by replacing it
	gitObj.delete_remote("origin")
	origin = gitObj.create_remote("origin", url="https://" + admin[1] + ":" + admin[2] + "@documentiaperti.org/" + repoInfos[2] + "/" + repoInfos[0] + ".git")

	#Pushing the new repository
	origin.push(refspec='{}:{}'.format("master", "master"))

	#Remove git folder
	rmtree(tempFolder)

	gitObj.close()

def renameAfterRemove(index, subFolderPath):
	maxVal = max(int(image.split(".")[0]) for image in os.listdir(subFolderPath))
	while index < maxVal:
		os.rename(os.path.join(subFolderPath, str(index+1) + ".jpg"), os.path.join(subFolderPath, str(index) + ".jpg"))
		index += 1

def getPhase():
	return pySIC.getPhase()