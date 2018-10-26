#Libraries
import json																# Library to elaborate JSON texts
import re 																# to parse string data
import os 																# Low level library to work with directories
from threading 			import Thread 									# to create threads
from git 				import Repo 									# to work with gitea's repositories
from urllib.parse 		import quote_plus 								# to translate a string into an URI string
from shutil 			import rmtree									# high level library to work on directories
from flask_cors 		import CORS 									# to handle browsers' CORS requests
from flask 				import Flask,request,make_response,redirect 	# to handle http requests
from pymysql 			import connect as sqlConnect					# to query database data
from time 				import sleep as timeSleep 						# to set check frequence of new jobs
from time 				import time as getCurrentTime 					# to get current timestamp
from requests 			import get as httpGet 							# to make http GET requests
from internetarchive 	import get_user_info as iaGetUserInfo 			# to get user infos on archive.org
from gc 				import collect									# to collect garbage after elaborations

# Pythons
from runCrop 			import *
from uiFunctions		import *
from dbQueryFunctions	import *

# Setting Flask and CORS
app = Flask(__name__)
CORS(app)

# Jobs queue
queue = []

# Actual job
actJob = None

# Debug mode
debug = False

# Database object
db = DataBase(sqlConnect(host="documentiaperti.org", user="user", passwd="passwd"), True)

def elabQueue():
	"""
	note:: This function check every 2 seconds jobs queue and will do related actions based on the requested job
	"""
	global queue
	global actJob
	while True:
		if debug: print(queue)
		# This is done because after some time db will release inactive connection
		#	Doing random query will prevent db to release connection 
		db.Ping() 
		if len(queue) == 0:
			timeSleep(2)
			continue
		project = queue.pop(0)
		actJob = project
		if project["operation"] == 1:
			cropAndOCR(project["idRepo"], project["uid"], project["params"]["language"], db, debug = debug)
		elif project["operation"] == 2:
			HOCR(project["idRepo"], project["uid"], project["params"]["hocrdata"], db)
		elif project["operation"] == 3:
			uploadPDFOnArchive(project["idRepo"], project["uid"], project["params"]["linkRepo"], db)
		actJob = None
		collect()

## Web

def auth(uid,cookieVal):
	"""
	:param uid: id of the user that wants to authenticate
	:param cookieVal: csrf cookie value for authentication
	:type uid: int
	:type cookieVal: str
	:returns: True, False
	:rtype: bool

	note:: Function for checking correct authentication on website for request mades through it
	"""

	return httpGet("https://documentiaperti.org/user/settings", allow_redirects=True, cookies={"documenti_aperti":cookieVal}).url == "https://documentiaperti.org/user/settings"

"""
###  Flask
	All the next functions can be called by an HTTP request which is generally made with a simple HTML form on the website.
	Every form has inside it some basic values like the repo's id for determining the working repository and the user's id
	that requested the action. Additional values are added depending to the requested action (i.e. keys for updating 
	archive.org account). Since all requests are made through web all of them, except the first, return to the origin page 
	where the user send the request, sending a cookie with the result of the action that can be displayed by gitea.
"""

#### HOCR

@app.route('/updateHOCR', methods=['POST'])
def updateHOCR():
	"""
	note:: Function called whenever a user wants to save an edited HOCR file, that add a job to jobs queue
	"""
	uid = request.form.get("user", type=int)
	if not auth(uid, request.cookies["documenti_aperti"]):
		return "Si e' verificato un errore di sistema", 401
	idRepo = request.form.get("idProject", type=int)
	if not db.actionOnRepo(uid, idRepo):
		return "Non hai i permessi necessari per eseguire modifiche su questa repository.", 403
	queue.append({"idRepo": idRepo, "uid": uid, "operation": 2, "params": {"hocrdata":request.form.get("hocrData")}})
	return "Ok", 200

#### archive.org

@app.route('/updateS3Key', methods=['POST'])
def updateS3Key():
	"""
	note:: Function called whenever a user wants to update his archive.org API keys
	"""
	cursor = db.getCursor()

	response = make_response(redirect('https://documentiaperti.org/user/settings'))
	try:
		uid = request.form.get("uid", type=int)
		if not auth(uid,request.cookies["documenti_aperti"]):
			response.set_cookie('macaron_flash', quote_plus("error=Si è verificato un errore di sistema."), max_age=1)
			return response
		if len(request.form.get("s3access")) != 16 or len(request.form.get("s3key")) != 16:
			response.set_cookie('macaron_flash', quote_plus("error=Le due chiavi devono avere una lunghezza di 16 caratteri."), max_age=1)
			return response
		if len(re.findall("[a-zA-Z0-9]\w*", request.form.get("s3access"))) != 1 or len(re.findall("[a-zA-Z0-9]\w*", request.form.get("s3key"))) != 1:
			response.set_cookie('macaron_flash', quote_plus("error=Le due chiavi devono contenere solo numeri e/o lettere."), max_age=1)
			return response
		if cursor.execute("SELECT 1 FROM gitea.archiveorg WHERE uid=%s", (uid,)) == 0:
			cursor.execute("INSERT INTO gitea.archiveorg (uid, s3access, s3key) VALUES (%s,%s,%s)", (uid, request.form.get("s3access"), request.form.get("s3key"),))
		else:
			cursor.execute("UPDATE gitea.archiveorg SET s3access=%s,s3key=%s WHERE uid=%s", (request.form.get("s3key"), request.form.get("s3key"), uid,))
		response.set_cookie('macaron_flash', quote_plus("success=Chiavi archive.org aggiornate."), max_age=1)
		return response
	except:
		response.set_cookie('macaron_flash', quote_plus("error=Si è verificato un errore nell'elaborazione della richiesta."), max_age=1)
		return response

@app.route('/uploadArchive', methods=['POST'])
def uploadArchive():
	"""
	note:: Function called whenever a user wants to update a PDF file from a release in archive.org
	"""
	response = make_response(redirect(request.form.get("redirectTo")))
	try:
		cursor = db.getCursor()

		uid = request.form.get("uid", type=int)
		if not auth(uid,request.cookies["documenti_aperti"]):
			response.set_cookie('macaron_flash', quote_plus("error=Si è verificato un errore di sistema."), max_age=1)
			return response

		idRepo = request.form.get("idRepo", type=int)
		if not db.actionOnRepo(uid,idRepo):
			response.set_cookie('macaron_flash', quote_plus("error=Non possiedi i permessi per inviare richieste."), max_age=1)
			return response

		if cursor.execute("SELECT s3access,s3key FROM gitea.archiveorg WHERE uid=%s",(uid,)) == 0:
			response.set_cookie('macaron_flash', quote_plus("error=Non hai impostato le chiavi necessarie per abilitare il sistema a modifiche sul tuo account archive.org. Puoi aggiungerle adesso nella scheda Profilo delle tue impostazioni."), max_age=1)
			return response
		s3Data = cursor.fetchone()

		try:
			iaGetUserInfo(access_key=s3Data[0], secret_key=s3Data[1])
		except:
			response.set_cookie('macaron_flash', quote_plus("error=Le chiavi indicate nelle impostazioni non sono valide. Puoi aggiornarle adesso nella scheda Profilo delle tue impostazioni."), max_age=1)
			return response

		queue.append({"operation":3,"uid":uid,"idRepo":idRepo,"params":{"linkRepo":request.form.get("branchLink")}})
		response.set_cookie('macaron_flash', quote_plus("success=La richiesta di caricamento è stata inviata."), max_age=1)
		return response
	except:
		response.set_cookie('macaron_flash', quote_plus("error=Si è verificato un errore nell'elaborazione della richiesta."), max_age=1)
		return response

@app.route('/updateRepo', methods=['POST'])
def updateRepo():
	"""
	note:: Function called whenever a user wants to update his archive.org API keys
	"""
	response = make_response(redirect(request.form.get("redirectTo")))
	try:
		uid = request.form.get("uid", type=int)
		if not auth(uid,request.cookies["documenti_aperti"]):
			response.set_cookie('macaron_flash', quote_plus("error=Si è verificato un errore di sistema."), max_age=10)
			return response

		idRepo = request.form.get("idRepo", type=int)
		if not db.actionOnRepo(uid,idRepo):
			response.set_cookie('macaron_flash', quote_plus("error=Non possiedi i permessi per inviare richieste."), max_age=10)
			return response

		if not all([operation["uid"] != uid for operation in queue]) or (actJob != None and actJob["uid"] == uid):
			response.set_cookie('macaron_flash', quote_plus("error=Hai già una richiesta di elaborazione attiva o in coda."), max_age=10)
			return response

		if not all([operation["idRepo"] != idRepo for operation in queue]) or (actJob != None and actJob["idRepo"] == idRepo):
			response.set_cookie('macaron_flash', quote_plus("error=Questa repository ha già una richiesta di elaborazione attiva o in coda."), max_age=10)
			return response

		dataToSend = {"idRepo": idRepo,"uid": uid,"operation": 1,"params": {"language": request.form.get("lang")}}
		queue.append(dataToSend)
		response.set_cookie('macaron_flash', quote_plus("success=La richiesta di elaborazione è stata inviata correttamente. Eventuali modifiche apportate prima della fine di essa verranno annullate."), max_age=10)
		return response
	except:
		response.set_cookie('macaron_flash', quote_plus("error=Si è verificato un errore nell'elaborazione della richiesta."), max_age=10)
		return response

@app.route('/getElaborationInfo', methods=['GET'])
def getElaborationInfo():
	"""
	note:: Function called every 2 seconds on main page of a repository for checking if this was submitted for elaboration
	"""
	global queue
	global actJob
	#try:
	if actJob != None and str(actJob["idRepo"]) == request.args["repoId"]:
		ph = getPhase()
		if ph:
			return json.dumps({"index": -1, "phase": ph[0], "perc": ph[1]}), 200
		return json.dumps({"index": -1, "phase": 0, "perc": 1}), 200
	index = next((c for c, item in enumerate(queue,1) if item["idRepo"] == request.args["repoId"]), None)
	if index:
		return json.dumps({"index": index}), 200
	return "Not found", 404
	#except:
		#return "Error", 500


"""
#### Raspberry PI
	This part is made only for working with the Raspberry Pi scanning tool.
"""

@app.route('/updateRepoRPI', methods=['POST'])
def updateRepoRPI():
	try:
		cursor = db.getCursor()

		uid = request.headers.get("user", type=int)
		passwd = request.headers.get("passwd")
		if cursor.execute("SELECT 1 FROM rPis_data.access WHERE uid=%s AND accessToken=%s",(uid, passwd,)) == 0:
			return "Unauthorized", 401

		data = json.loads(request.data.decode("utf-8"))
		queue.append({"idRepo": db.getRepoInfosbyName(uid,data["nameProject"])[2], "uid": uid, "operation": 1, "params": {"language": data["language"]}})
		return "Ok", 200
	except:
		return "Error", 500

t = Thread(target=elabQueue)
t.start()

if __name__ == '__main__':
	app.run(host='0.0.0.0', port=2020, debug=False, ssl_context=('/path/to/cert.pem', '/path/to/privkey.pem'))
