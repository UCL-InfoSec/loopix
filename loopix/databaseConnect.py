import sqlite3

def connectToDatabase(databaseName):
	conn = sqlite3.connect(databaseName)
	return conn

def createUsersTable(db, tableName):
	c = db.cursor()
	c.execute('''CREATE TABLE IF NOT EXISTS %s (id INTEGER PRIMARY KEY, name text, port integer, host text, pubk blob, provider blob)'''%tableName)
	db.commit()
	print "Table [%s] created succesfully." % tableName

def createProvidersTable(db, tableName):
	c = db.cursor()
	c.execute('''CREATE TABLE IF NOT EXISTS %s (id INTEGER PRIMARY KEY, name text, port integer, host text, pubk blob)'''%tableName)
	db.commit()
	print "Table [%s] created succesfully." % tableName

def createMixnodesTable(db, tableName):
	c = db.cursor()
	c.execute('''CREATE TABLE IF NOT EXISTS %s (id INTEGER PRIMARY KEY, name text, port integer, host text, pubk blob)'''%tableName)
	db.commit()
	print "Table [%s] created succesfully." % tableName	

def dropTabel(db, tableName):
	c = db.cursor()
	c.execute("DROP TABLE IF EXISTS %s"%tableName)
	db.commit()
	print "Tabel [%s] droped succesfully." % tableName

def selectAll(tableName):
	return "SELECT * FROM %s" % tableName

def selectByIdx(db, tableName, idx):
	c = db.cursor()
	c.execute("SELECT * FROM %s WHERE id=%d" % (tableName, idx))	
	return c.fetchone()

def countRows(db, tableName):
	c = db.cursor()
	c.execute("SELECT Count(*) FROM %s" % tableName)
	return int(c.fetchone()[0])
