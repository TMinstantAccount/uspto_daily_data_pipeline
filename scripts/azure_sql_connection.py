"""
Azure SQL Database Connection Script
Connects to Azure SQL Database using pyodbc
Supports both SQL Server Authentication and Azure AD Authentication
"""

import pyodbc
from typing import Optional, List, Dict, Any
import urllib.parse
import sys
import os
import logging

# Set up logging
logger = logging.getLogger(__name__)

# Fix Unicode encoding for Windows console
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass


class AzureSQLConnection:
    """Class to handle Azure SQL Database connections"""
    
    def __init__(self, connection_string: Optional[str] = None, 
                 server: Optional[str] = None,
                 database: Optional[str] = None,
                 auth_method: str = "sql_server",
                 username: Optional[str] = None,
                 password: Optional[str] = None,
                 azure_account: Optional[str] = None):
        """
        Initialize connection with Azure SQL Database
        
        Args:
            connection_string: Full connection string (for SQL Server auth)
            server: Server name (e.g., tminstant-sqlserver.database.windows.net)
            database: Database name (e.g., TMinstantSales)
            auth_method: "sql_server" or "azure_ad"
            username: SQL Server username (for sql_server auth)
            password: SQL Server password (for sql_server auth)
            azure_account: Azure AD account email (for azure_ad auth)
        """
        self.connection_string = connection_string
        self.server = server
        self.database = database
        self.auth_method = auth_method
        self.username = username
        self.password = password
        self.azure_account = azure_account
        self.conn: Optional[pyodbc.Connection] = None
        
        # Build connection string if parameters provided
        if not connection_string and server and database:
            if auth_method == "sql_server" and username and password:
                self.connection_string = self._build_sql_auth_string()
            elif auth_method == "azure_ad":
                self.connection_string = self._build_azure_ad_string()
    
    def _build_sql_auth_string(self) -> str:
        """Build connection string for SQL Server authentication"""
        # Build connection string with proper escaping
        # For usernames with @ symbol, ensure proper formatting
        # Try Driver 18 first (commonly available), fallback to Driver 17
        return (
            f"DRIVER={{ODBC Driver 18 for SQL Server}};"
            f"SERVER=tcp:{self.server},1433;"
            f"DATABASE={self.database};"
            f"UID={self.username};"
            f"PWD={self.password};"
            f"Encrypt=yes;"
            f"TrustServerCertificate=no;"
            f"Connection Timeout=30;"
        )
    
    def _build_azure_ad_string(self) -> str:
        """Build connection string for Azure AD authentication"""
        # For Azure AD with MFA, use ActiveDirectoryInteractive
        # Note: DRIVER must be specified separately when connecting
        conn_str = (
            f"DRIVER={{ODBC Driver 18 for SQL Server}};"
            f"SERVER=tcp:{self.server},1433;"
            f"DATABASE={self.database};"
            f"Authentication=ActiveDirectoryInteractive;"
            f"Encrypt=yes;"
            f"TrustServerCertificate=no;"
        )
        # Add UID if Azure account is provided
        if self.azure_account:
            conn_str += f"UID={self.azure_account};"
        return conn_str
        
    def connect(self) -> bool:
        """
        Establish connection to the database
        
        Returns:
            True if connection successful, False otherwise
        """
        if not self.connection_string:
            error_msg = "No connection string available. Provide connection_string or connection parameters."
            logger.error(error_msg)
            return False
        
        try:
            if self.auth_method == "azure_ad":
                # For Azure AD, use ActiveDirectoryInteractive authentication
                # This will prompt for MFA if required
                logger.info("Connecting using Azure AD authentication...")
                logger.info("You may be prompted to authenticate in your browser.")
                
                # Use the pre-built connection string or build it now
                if not self.connection_string:
                    self.connection_string = self._build_azure_ad_string()
                
                self.conn = pyodbc.connect(self.connection_string, timeout=30)
            else:
                # SQL Server authentication
                logger.info("Connecting using SQL Server authentication...")
                logger.info(f"Server: {self.server}")
                logger.info(f"Database: {self.database}")
                logger.info(f"Username: {self.username}")
                
                # For usernames with @ symbol, pyodbc can misinterpret it
                # Solution: Use connection string with proper parameter order
                # Ensure SERVER is specified first and clearly
                
                # For Azure SQL Database SQL Server authentication:
                # If username contains @, it might be a contained database user
                # Try the username as-is first, but pyodbc may misinterpret @
                # Solution: Use connection string with SERVER specified clearly first
                
                # Try with the username as provided
                try:
                    conn_str = (
                        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
                        f"SERVER=tcp:{self.server},1433;"
                        f"DATABASE={self.database};"
                        f"UID={self.username};"
                        f"PWD={self.password};"
                        f"Encrypt=yes;"
                        f"TrustServerCertificate=no;"
                        f"Connection Timeout=30;"
                    )
                    self.conn = pyodbc.connect(conn_str, timeout=30)
                except pyodbc.Error as e:
                    # If username with @ fails, try without domain part
                    # For SQL Server auth, sometimes only the username part is needed
                    if "@" in self.username and "Cannot open server" in str(e):
                        logger.info("Username contains @, trying username without domain...")
                        username_only = self.username.split("@")[0]
                        conn_str = (
                            f"DRIVER={{ODBC Driver 18 for SQL Server}};"
                            f"SERVER=tcp:{self.server},1433;"
                            f"DATABASE={self.database};"
                            f"UID={username_only};"
                            f"PWD={self.password};"
                            f"Encrypt=yes;"
                            f"TrustServerCertificate=no;"
                            f"Connection Timeout=30;"
                        )
                        self.conn = pyodbc.connect(conn_str, timeout=30)
                    else:
                        raise
            
            logger.info("Successfully connected to Azure SQL Database")
            return True
        except pyodbc.Error as e:
            error_msg = f"Connection error: {e}"
            logger.error(error_msg)
            if "Authentication" in str(e) or "login" in str(e).lower():
                logger.error("For SQL Server authentication, make sure:")
                logger.error("  1. You have ODBC Driver 17 or 18 for SQL Server installed")
                logger.error("  2. Username and password are correct")
                logger.error("  3. Your IP address is allowed in Azure SQL firewall rules")
                logger.error("  4. The SQL login exists and has proper permissions")
            # Raise exception with detailed error message
            raise Exception(error_msg)
        except Exception as e:
            error_msg = f"Unexpected connection error: {e}"
            logger.error(error_msg)
            raise Exception(error_msg)
    
    def test_connection(self) -> bool:
        """
        Test the database connection by executing a simple query
        
        Returns:
            True if test successful, False otherwise
        """
        if not self.conn:
            error_msg = "No active connection. Call connect() first."
            logger.error(error_msg)
            raise Exception(error_msg)
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT @@VERSION")
            version = cursor.fetchone()[0]
            logger.info("Connection test successful!")
            logger.info(f"Database version: {version[:100]}...")
            cursor.close()
            return True
        except Exception as e:
            error_msg = f"Connection test failed: {e}"
            logger.error(error_msg)
            raise Exception(error_msg)
    
    def execute_query(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        """
        Execute a SELECT query and return results as list of dictionaries
        
        Args:
            query: SQL query string
            params: Optional tuple of parameters for parameterized queries
            
        Returns:
            List of dictionaries where each dict represents a row
        """
        if not self.conn:
            raise Exception("No active connection. Call connect() first.")
        
        cursor = self.conn.cursor()
        try:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            # Get column names
            columns = [column[0] for column in cursor.description]
            
            # Fetch all rows and convert to list of dicts
            rows = cursor.fetchall()
            results = [dict(zip(columns, row)) for row in rows]
            
            return results
        finally:
            cursor.close()
    
    def execute_non_query(self, query: str, params: Optional[tuple] = None) -> int:
        """
        Execute INSERT, UPDATE, DELETE queries
        
        Args:
            query: SQL query string
            params: Optional tuple of parameters for parameterized queries
            
        Returns:
            Number of rows affected
        """
        if not self.conn:
            raise Exception("No active connection. Call connect() first.")
        
        cursor = self.conn.cursor()
        try:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            self.conn.commit()
            return cursor.rowcount
        except Exception as e:
            self.conn.rollback()
            raise e
        finally:
            cursor.close()
    
    def list_tables(self) -> List[str]:
        """
        List all tables in the database
        
        Returns:
            List of table names
        """
        query = """
        SELECT TABLE_NAME 
        FROM INFORMATION_SCHEMA.TABLES 
        WHERE TABLE_TYPE = 'BASE TABLE'
        ORDER BY TABLE_NAME
        """
        results = self.execute_query(query)
        return [row['TABLE_NAME'] for row in results]
    
    def get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        """
        Get column information for a specific table
        
        Args:
            table_name: Name of the table
            
        Returns:
            List of dictionaries with column information
        """
        query = """
        SELECT 
            COLUMN_NAME,
            DATA_TYPE,
            CHARACTER_MAXIMUM_LENGTH,
            IS_NULLABLE,
            COLUMN_DEFAULT
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = ?
        ORDER BY ORDINAL_POSITION
        """
        return self.execute_query(query, (table_name,))
    
    def close(self):
        """Close the database connection"""
        if self.conn:
            self.conn.close()
            self.conn = None
            logger.info("Connection closed")
    
    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()


def main():
    """Main function to test the connection"""
    
    print("=" * 60)
    print("Azure SQL Database Connection Test")
    print("=" * 60)
    print("\nUsing SQL Server Authentication")
    print("=" * 60)
    
    # SQL Server Authentication with provided credentials
    db = AzureSQLConnection(
        server="tminstant-sqlserver.database.windows.net",
        database="TMinstantSales",
        auth_method="sql_server",
        username="airflow_sql_login",
        password="Aq9!_tR7#xL3@pV8$zN2"
    )
    
    # Test connection using context manager
    try:
        with db:
            # Test connection
            if db.test_connection():
                print("\n" + "-" * 60)
                print("Listing tables in database:")
                print("-" * 60)
                
                tables = db.list_tables()
                if tables:
                    print(f"Found {len(tables)} tables:")
                    for table in tables[:10]:  # Show first 10 tables
                        print(f"  - {table}")
                    if len(tables) > 10:
                        print(f"  ... and {len(tables) - 10} more")
                else:
                    print("No tables found in database")
                
                # Example: Get info for first table if available
                if tables:
                    print(f"\n" + "-" * 60)
                    print(f"Table structure for '{tables[0]}':")
                    print("-" * 60)
                    columns = db.get_table_info(tables[0])
                    for col in columns:
                        print(f"  {col['COLUMN_NAME']}: {col['DATA_TYPE']} "
                              f"({'NULL' if col['IS_NULLABLE'] == 'YES' else 'NOT NULL'})")
                
                # Example query
                print(f"\n" + "-" * 60)
                print("Example: Getting database name")
                print("-" * 60)
                result = db.execute_query("SELECT DB_NAME() AS DatabaseName")
                print(f"Current database: {result[0]['DatabaseName']}")
                
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        print("\nTroubleshooting tips:")
        print("1. Make sure pyodbc is installed: pip install pyodbc")
        print("2. On Windows, you may need ODBC Driver 17 or 18 for SQL Server")
        print("3. Check firewall rules allow your IP to access Azure SQL")
        print("4. Verify username and password are correct")
        print("5. Ensure the SQL login exists and has proper database permissions")


if __name__ == "__main__":
    main()
