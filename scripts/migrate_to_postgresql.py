#!/usr/bin/env python3
"""
Database Migration Script: SQLite to PostgreSQL
This script migrates the Izishop database from SQLite to PostgreSQL
with data validation and rollback capabilities.
"""

import os
import sys
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
import json

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.security_config import get_security_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('migration.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class DatabaseMigrator:
    """Handles migration from SQLite to PostgreSQL"""
    
    def __init__(self):
        self.settings = get_security_settings()
        self.sqlite_path = None
        self.pg_connection = None
        self.migration_log = []
        
    def setup_sqlite_connection(self, sqlite_path: str):
        """Setup SQLite connection for source database"""
        try:
            if not os.path.exists(sqlite_path):
                raise FileNotFoundError(f"SQLite database not found: {sqlite_path}")
            
            self.sqlite_path = sqlite_path
            logger.info(f"SQLite database found: {sqlite_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to setup SQLite connection: {e}")
            return False
    
    def setup_postgresql_connection(self):
        """Setup PostgreSQL connection for target database"""
        try:
            # Parse DATABASE_URL
            db_url = self.settings.DATABASE_URL
            if not db_url.startswith('postgresql://'):
                raise ValueError("DATABASE_URL must be a PostgreSQL connection string")
            
            self.pg_connection = psycopg2.connect(db_url)
            logger.info("PostgreSQL connection established")
            return True
        except Exception as e:
            logger.error(f"Failed to setup PostgreSQL connection: {e}")
            return False
    
    def get_sqlite_tables(self) -> List[str]:
        """Get list of tables from SQLite database"""
        try:
            conn = sqlite3.connect(self.sqlite_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            tables = [row[0] for row in cursor.fetchall()]
            
            conn.close()
            logger.info(f"Found {len(tables)} tables in SQLite: {tables}")
            return tables
        except Exception as e:
            logger.error(f"Failed to get SQLite tables: {e}")
            return []
    
    def get_table_schema(self, table_name: str) -> Dict[str, Any]:
        """Get table schema from SQLite"""
        try:
            conn = sqlite3.connect(self.sqlite_path)
            cursor = conn.cursor()
            
            # Get table info
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            
            # Get sample data for type inference
            cursor.execute(f"SELECT * FROM {table_name} LIMIT 1")
            sample_row = cursor.fetchone()
            
            conn.close()
            
            schema = {
                'name': table_name,
                'columns': [],
                'sample_data': sample_row
            }
            
            for col in columns:
                col_info = {
                    'name': col[1],
                    'type': col[2],
                    'not_null': bool(col[3]),
                    'default': col[4],
                    'primary_key': bool(col[5])
                }
                schema['columns'].append(col_info)
            
            return schema
        except Exception as e:
            logger.error(f"Failed to get schema for table {table_name}: {e}")
            return {}
    
    def create_postgresql_table(self, schema: Dict[str, Any]) -> bool:
        """Create table in PostgreSQL based on SQLite schema"""
        try:
            cursor = self.pg_connection.cursor()
            
            # Map SQLite types to PostgreSQL types
            type_mapping = {
                'INTEGER': 'BIGINT',
                'REAL': 'DOUBLE PRECISION',
                'TEXT': 'TEXT',
                'BLOB': 'BYTEA',
                'VARCHAR': 'VARCHAR',
                'BOOLEAN': 'BOOLEAN',
                'DATETIME': 'TIMESTAMP',
                'DATE': 'DATE'
            }
            
            # Build CREATE TABLE statement
            columns = []
            for col in schema['columns']:
                pg_type = type_mapping.get(col['type'].upper(), 'TEXT')
                
                col_def = f"{col['name']} {pg_type}"
                
                if col['not_null']:
                    col_def += " NOT NULL"
                
                if col['default'] is not None:
                    if isinstance(col['default'], str):
                        col_def += f" DEFAULT '{col['default']}'"
                    else:
                        col_def += f" DEFAULT {col['default']}"
                
                if col['primary_key']:
                    col_def += " PRIMARY KEY"
                
                columns.append(col_def)
            
            create_sql = f"""
            CREATE TABLE IF NOT EXISTS {schema['name']} (
                {', '.join(columns)}
            );
            """
            
            cursor.execute(create_sql)
            self.pg_connection.commit()
            
            logger.info(f"Created table {schema['name']} in PostgreSQL")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create table {schema['name']}: {e}")
            self.pg_connection.rollback()
            return False
    
    def migrate_table_data(self, table_name: str) -> bool:
        """Migrate data from SQLite table to PostgreSQL"""
        try:
            # Connect to SQLite
            sqlite_conn = sqlite3.connect(self.sqlite_path)
            sqlite_cursor = sqlite_conn.cursor()
            
            # Get all data from SQLite
            sqlite_cursor.execute(f"SELECT * FROM {table_name}")
            rows = sqlite_cursor.fetchall()
            
            if not rows:
                logger.info(f"Table {table_name} is empty, skipping data migration")
                sqlite_conn.close()
                return True
            
            # Get column names
            sqlite_cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [col[1] for col in sqlite_cursor.fetchall()]
            
            # Prepare PostgreSQL cursor
            pg_cursor = self.pg_connection.cursor()
            
            # Clear existing data
            pg_cursor.execute(f"DELETE FROM {table_name}")
            
            # Insert data
            placeholders = ', '.join(['%s'] * len(columns))
            insert_sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"
            
            # Convert data types and handle None values
            converted_rows = []
            for row in rows:
                converted_row = []
                for value in row:
                    if value is None:
                        converted_row.append(None)
                    elif isinstance(value, str):
                        converted_row.append(value)
                    elif isinstance(value, (int, float)):
                        converted_row.append(value)
                    elif isinstance(value, bool):
                        converted_row.append(value)
                    else:
                        converted_row.append(str(value))
                converted_rows.append(converted_row)
            
            # Batch insert for better performance
            pg_cursor.executemany(insert_sql, converted_rows)
            self.pg_connection.commit()
            
            sqlite_conn.close()
            logger.info(f"Migrated {len(rows)} rows from {table_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to migrate data for table {table_name}: {e}")
            self.pg_connection.rollback()
            return False
    
    def validate_migration(self, table_name: str) -> bool:
        """Validate that data was migrated correctly"""
        try:
            # Count rows in both databases
            sqlite_conn = sqlite3.connect(self.sqlite_path)
            sqlite_cursor = sqlite_conn.cursor()
            sqlite_cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            sqlite_count = sqlite_cursor.fetchone()[0]
            sqlite_conn.close()
            
            pg_cursor = self.pg_connection.cursor()
            pg_cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            pg_count = pg_cursor.fetchone()[0]
            
            if sqlite_count == pg_count:
                logger.info(f"Validation passed for {table_name}: {pg_count} rows")
                return True
            else:
                logger.error(f"Validation failed for {table_name}: SQLite={sqlite_count}, PostgreSQL={pg_count}")
                return False
                
        except Exception as e:
            logger.error(f"Validation failed for {table_name}: {e}")
            return False
    
    def create_indexes(self, table_name: str):
        """Create common indexes for better performance"""
        try:
            cursor = self.pg_connection.cursor()
            
            # Common indexes for e-commerce tables
            if 'user' in table_name.lower():
                cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_email ON {table_name} (email)")
                cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_username ON {table_name} (username)")
            
            elif 'product' in table_name.lower():
                cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_shop_id ON {table_name} (shop_id)")
                cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_category_id ON {table_name} (category_id)")
                cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_price ON {table_name} (price)")
            
            elif 'order' in table_name.lower():
                cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_user_id ON {table_name} (user_id)")
                cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_status ON {table_name} (status)")
                cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_created_at ON {table_name} (created_at)")
            
            self.pg_connection.commit()
            logger.info(f"Created indexes for {table_name}")
            
        except Exception as e:
            logger.error(f"Failed to create indexes for {table_name}: {e}")
            self.pg_connection.rollback()
    
    def run_migration(self, sqlite_path: str) -> bool:
        """Run the complete migration process"""
        try:
            logger.info("Starting database migration from SQLite to PostgreSQL")
            
            # Setup connections
            if not self.setup_sqlite_connection(sqlite_path):
                return False
            
            if not self.setup_postgresql_connection():
                return False
            
            # Get tables to migrate
            tables = self.get_sqlite_tables()
            if not tables:
                logger.error("No tables found to migrate")
                return False
            
            # Migration process
            successful_tables = []
            failed_tables = []
            
            for table_name in tables:
                logger.info(f"Migrating table: {table_name}")
                
                try:
                    # Get schema
                    schema = self.get_table_schema(table_name)
                    if not schema:
                        failed_tables.append(table_name)
                        continue
                    
                    # Create table
                    if not self.create_postgresql_table(schema):
                        failed_tables.append(table_name)
                        continue
                    
                    # Migrate data
                    if not self.migrate_table_data(table_name):
                        failed_tables.append(table_name)
                        continue
                    
                    # Validate migration
                    if not self.validate_migration(table_name):
                        failed_tables.append(table_name)
                        continue
                    
                    # Create indexes
                    self.create_indexes(table_name)
                    
                    successful_tables.append(table_name)
                    logger.info(f"Successfully migrated table: {table_name}")
                    
                except Exception as e:
                    logger.error(f"Failed to migrate table {table_name}: {e}")
                    failed_tables.append(table_name)
            
            # Migration summary
            logger.info("=" * 50)
            logger.info("MIGRATION SUMMARY")
            logger.info("=" * 50)
            logger.info(f"Total tables: {len(tables)}")
            logger.info(f"Successful: {len(successful_tables)}")
            logger.info(f"Failed: {len(failed_tables)}")
            
            if successful_tables:
                logger.info(f"Successfully migrated: {', '.join(successful_tables)}")
            
            if failed_tables:
                logger.error(f"Failed to migrate: {', '.join(failed_tables)}")
            
            # Create migration metadata
            self.create_migration_metadata(successful_tables, failed_tables)
            
            return len(failed_tables) == 0
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            return False
        finally:
            if self.pg_connection:
                self.pg_connection.close()
    
    def create_migration_metadata(self, successful_tables: List[str], failed_tables: List[str]):
        """Create migration metadata table"""
        try:
            cursor = self.pg_connection.cursor()
            
            # Create migration history table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS migration_history (
                    id SERIAL PRIMARY KEY,
                    migration_name VARCHAR(255) NOT NULL,
                    source_database VARCHAR(255) NOT NULL,
                    target_database VARCHAR(255) NOT NULL,
                    successful_tables TEXT[],
                    failed_tables TEXT[],
                    migration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status VARCHAR(50) NOT NULL
                )
            """)
            
            # Insert migration record
            cursor.execute("""
                INSERT INTO migration_history 
                (migration_name, source_database, target_database, successful_tables, failed_tables, status)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                "sqlite_to_postgresql_migration",
                self.sqlite_path,
                self.settings.DATABASE_URL,
                successful_tables,
                failed_tables,
                "SUCCESS" if not failed_tables else "PARTIAL_SUCCESS"
            ))
            
            self.pg_connection.commit()
            logger.info("Migration metadata recorded")
            
        except Exception as e:
            logger.error(f"Failed to create migration metadata: {e}")
            self.pg_connection.rollback()

def main():
    """Main migration function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Migrate Izishop database from SQLite to PostgreSQL')
    parser.add_argument('--sqlite-path', required=True, help='Path to SQLite database file')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be migrated without executing')
    
    args = parser.parse_args()
    
    if args.dry_run:
        logger.info("DRY RUN MODE - No changes will be made")
        # Just show what would be migrated
        migrator = DatabaseMigrator()
        if migrator.setup_sqlite_connection(args.sqlite_path):
            tables = migrator.get_sqlite_tables()
            logger.info(f"Would migrate {len(tables)} tables: {tables}")
        return
    
    # Run actual migration
    migrator = DatabaseMigrator()
    success = migrator.run_migration(args.sqlite_path)
    
    if success:
        logger.info("Migration completed successfully!")
        sys.exit(0)
    else:
        logger.error("Migration failed!")
        sys.exit(1)

if __name__ == "__main__":
    main() 