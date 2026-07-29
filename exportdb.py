from PyQt5.QtSql import QSqlDatabase, QSqlQuery
import mysql.connector

def copy_data_from_sqlite_to_mysql(sqlite_db_name, mysql_db_name):
    # Membuka koneksi ke database SQLite
    sqlite_db = QSqlDatabase.addDatabase("QSQLITE")
    sqlite_db.setDatabaseName(sqlite_db_name)

    if not sqlite_db.open():
        print("Tidak dapat membuka database SQLite")
        return

    # Membuka koneksi ke database MySQL
    mysql_conn = mysql.connector.connect(
        host='localhost',
        user='root',
        password='',
        database=mysql_db_name
    )
    mysql_cursor = mysql_conn.cursor()

    query = QSqlQuery()

    # Mendapatkan data dari SQLite tanpa kolom 'id'
    data_query = QSqlQuery(f"SELECT Tanggal, Waktu, Lokasi, Bukti FROM data;")
    while data_query.next():
        values = [data_query.value(i) for i in range(data_query.record().count())]
        placeholders = ', '.join(['%s'] * len(values))
        insert_query = f"INSERT INTO data (Tanggal, Waktu, Lokasi, Bukti) VALUES ({placeholders});"
        mysql_cursor.execute(insert_query, values)

    # Commit perubahan ke MySQL dan menutup koneksi
    mysql_conn.commit()
    mysql_conn.close()

    # Menutup koneksi SQLite
    sqlite_db.close()
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    
if __name__ == "__main__":
    sqlite_db_name = "logging.db"
    mysql_db_name = "ppe"
    copy_data_from_sqlite_to_mysql(sqlite_db_name, mysql_db_name)
