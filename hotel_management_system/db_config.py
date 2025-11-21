import MySQLdb
def get_db_connection():
    return MySQLdb.connect (
        host = "localhost",
        user = "root",
        passwd = "12345678",
        database = "hotel_db",
    )