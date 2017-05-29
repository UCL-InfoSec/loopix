import sqlite3
from format3 import Mix, Provider, User
import petlib.pack

class DatabaseManager(object):
	def __init__(self, databaseName):
		self.db = sqlite3.connect(databaseName)
		self.cursor = self.db.cursor()

	def connectToDatabase(self, databaseName):
		conn = sqlite3.connect(databaseName)
		return conn

	def createUsersTable(self, tableName):
		self.cursor.execute('''CREATE TABLE IF NOT EXISTS %s (id INTEGER PRIMARY KEY, name blob, port integer, host text, pubk blob, provider blob)'''%tableName)
		self.db.commit()
		print "Table [%s] created succesfully." % tableName

	def createProvidersTable(self, tableName):
		self.cursor.execute('''CREATE TABLE IF NOT EXISTS %s (id INTEGER PRIMARY KEY, name blob, port integer, host text, pubk blob)'''%tableName)
		self.db.commit()
		print "Table [%s] created succesfully." % tableName

	def createMixnodesTable(self, tableName):
		self.cursor.execute('''CREATE TABLE IF NOT EXISTS %s (id INTEGER PRIMARY KEY, name blob, port integer, host text, pubk blob, groupId integer)'''%tableName)
		self.db.commit()
		print "Table [%s] created succesfully." % tableName

	def dropTabel(self, tableName):
		self.cursor.execute("DROP TABLE IF EXISTS %s"%tableName)
		print "Tabel [%s] droped succesfully." % tableName

	def insertRowIntoTable(self, tableName, params):
		insertQuery = "INSERT INTO %s VALUES (%s)" % (tableName, ', '.join('?' for p in params))
		self.cursor.execute(insertQuery, params)
		self.db.commit()

	def selectAll(self, tableName):
		self.cursor.execute("SELECT * FROM %s" % tableName)
		return self.cursor.fetchall()

	def selectByIdx(self, tableName, idx):
		self.cursor.execute("SELECT * FROM %s WHERE id=%d" % (tableName, idx))
		return c.fetchone()

	def select_all_mixnodes(self):
		mixesInfo = self.selectAll('Mixnodes')
		mixes = []
		for m in mixesInfo:
			mixes.append(Mix(m[1], m[2], m[3], petlib.pack.decode(m[4]), m[5]))
		return mixes

	def select_all_providers(self):
		providersInfo = self.selectAll('Providers')
		providers = []
		for p in providersInfo:
			providers.append(Provider(str(p[1]), p[2], str(p[3]), petlib.pack.decode(p[4])))
		return providers

	def select_all_clients(self):
		clientsInfo = self.selectAll('Users')
		clients = []
		for c in clientsInfo:
			provider = Provider(*petlib.pack.decode(c[5]))
			clients.append(User(str(c[1]), c[2], c[3], petlib.pack.decode(c[4]), provider))
		return clients

	def countRows(self, tableName):
		self.cursor.execute("SELECT Count(*) FROM %s" % tableName)
		return int(c.fetchone()[0])

	def close_connection(self):
		self.db.close()
