import random 															# to create random hashes

class DataBase():
	def __init__(self, _db, autoCommit):
		self._db = _db
		self._db.autocommit(autoCommit)

	def getCursor(self):
		return self._db.cursor()

	def Ping(self):
		self._db.ping()

	def getRepoInfos(self, repoId):
		cursor = self._db.cursor()
		if cursor.execute("SELECT name,owner_id FROM gitea.repository WHERE id=%s",(repoId,)) == 0:
			return None
		data = cursor.fetchone()
		name = data[0]
		own_id = data[1]
		return [name,own_id, self.getUserName(own_id)]

	def actionOnRepo(self, uid,repoId):
		cursor = self._db.cursor()
		if cursor.execute("SELECT 1 FROM gitea.repository WHERE id=%s AND owner_id=%s",(repoId,uid,)) == 0 and cursor.execute("SELECT 1 FROM gitea.access WHERE repo_id=%s AND user_id=%s AND (mode = 2 OR mode = 3)",(repoId,uid,)) == 0:
			return False
		return True

	def getUserName(self, uid):
		cursor = self._db.cursor()
		if cursor.execute("SELECT name FROM gitea.user WHERE id=%s",(uid,)) == 0:
			return None
		return cursor.fetchone()[0]

	def addCollaboration(self, repoId,uid,mode):
		cursor = self._db.cursor()
		if cursor.execute("SELECT 1 FROM gitea.collaboration WHERE repo_id=%s AND user_id=%s AND (mode=%s or mode=3)",(repoId,uid,mode,)) == 0:
			if cursor.execute("SELECT id FROM gitea.collaboration ORDER BY id DESC LIMIT 1") != 0: counter = int(cursor.fetchone()[0]) + 1
			else: counter = 0
			cursor.execute("INSERT INTO gitea.collaboration (id,repo_id,user_id,mode) VALUES (%s,%s,%s,%s)",(counter,repoId,uid,mode,))
			if cursor.execute("SELECT id FROM gitea.access ORDER BY id DESC LIMIT 1") != 0: counter = int(cursor.fetchone()[0]) + 1
			else: counter = 0
			cursor.execute("INSERT INTO gitea.access (id,repo_id,user_id,mode) VALUES (%s,%s,%s,%s)",(counter,repoId,uid,mode,))


	def getRepoInfosbyName(self, idOwner,nameRepo):
		cursor = self._db.cursor()
		if cursor.execute("SELECT id FROM gitea.repository WHERE owner_id=%s AND name=%s",(idOwner,nameRepo,)) == 0:
			return None
		return [nameRepo,idOwner,cursor.fetchone()[0]]

	def getAdmin(self):
		cursor = self._db.cursor()
		if cursor.execute("SELECT name,id FROM gitea.user WHERE is_admin=1") == 0:
			return None
		data = cursor.fetchone()
		name = data[0]
		uid = data[1]
		if cursor.execute("SELECT sha1 FROM gitea.access_token WHERE uid=%s",(uid,)) == 0:
			counter = cursor.execute("SELECT id FROM gitea.access_token") + 1
			token = "%032x" % random.getrandbits(128)
			cursor.execute("INSERT INTO gitea.access_token (id,uid,name,sha1,created_unix,updated_unix) VALUES (%s,%s,%s,%s,%s,%s)",(counter,uid,'SISTEMA - NON RIMUOVERE - DON\'T REMOVE',token,getCurrentTime(),getCurrentTime()))
		else:
			token = cursor.fetchone()[0]
		return [uid,name,token]
