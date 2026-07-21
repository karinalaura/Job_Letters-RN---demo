import csv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import datetime
import json
import pandas as pd

from models import Base, Person, PayRecord, Organisation


DATABASE_URL = "sqlite:///./sql_app.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def create_tables():
    """Creates all tables defined in Base.metadata."""
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully!")

def populate_persons_from_csv(file_path: str):
    """Populates the persons table from a CSV file."""
    db = SessionLocal()
    try:
        df = pd.read_csv(file_path, encoding='cp1252')
        
        for index, row in df.iterrows():
            # Convert date string to datetime.date object
            # Handle MM/DD/YYYY format
            try:
                enlistment_date = datetime.datetime.strptime(row['enlistment_date'], '%m/%d/%Y').date()
            except ValueError:
                # Try alternative format YYYY-MM-DD
                enlistment_date = datetime.datetime.strptime(row['enlistment_date'], '%Y-%m-%d').date()

            # Check if person already exists by badge_number
            existing_person = db.query(Person).filter(Person.badge_number == str(row['badge_number'])).first()
            if existing_person:
                print(f"Person with badge number {row['badge_number']} already exists. Skipping.")
                continue

            person = Person(
                emp_id=row['emp_id'],
                full_name=row['full_name'],
                nis=row.get('nis') if 'nis' in df.columns and pd.notna(row.get('nis')) else None, # Handle missing column and NaN values
                badge_number=str(row['badge_number']),
                email=row.get('email') if 'email' in df.columns and pd.notna(row.get('email')) else None,
                phone=row.get('phone') if 'phone' in df.columns and pd.notna(row.get('phone')) else None, # Handle missing column and NaN values
                rank=row['rank'],
                acting_rank=str(row.get('acting_rank')).strip() if 'acting_rank' in df.columns and pd.notna(row.get('acting_rank')) and str(row.get('acting_rank')).strip() != '' else None, # Handle missing column and NaN values
                department=row.get('department') if 'department' in df.columns and pd.notna(row.get('department')) else None,
                enlistment_date=enlistment_date
            )
            db.add(person)
        db.commit()
        print(f"Successfully populated {len(df)} persons from {file_path}")
    except Exception as e:
        db.rollback()
        print(f"Error populating persons from {file_path}: {e}")
    finally:
        db.close()

def populate_pay_records_from_csv(file_path: str):
    """Populates the pay_records table from a CSV file."""
    db = SessionLocal()
    try:
        df = pd.read_csv(file_path, thousands=',', encoding='cp1252')

        for index, row in df.iterrows():
            # Find the person by Ihris emp_id to link the pay record
            person = db.query(Person).filter(Person.emp_id == int(row['emp_id'])).first()
            if not person:
                print(f"Person with emp_id {row['emp_id']} not found for pay record in {file_path}. Skipping.")
                continue
            
            # Convert date string to datetime.date object
            # Handle multiple date formats
            period_end_str = str(row['period_end'])
            try:
                # Try MM/DD/YYYY or M/D/YY format
                if '/' in period_end_str:
                    parts = period_end_str.split('/')
                    if len(parts[2]) == 2:  # Two-digit year
                        period_end = datetime.datetime.strptime(period_end_str, '%d/%m/%y').date()
                    else:
                        period_end = datetime.datetime.strptime(period_end_str, '%m/%d/%Y').date()
                else:
                    period_end = datetime.datetime.strptime(period_end_str, '%Y-%m-%d').date()
            except ValueError:
                # Try DD/MM/YY format
                period_end = datetime.datetime.strptime(period_end_str, '%d/%m/%y').date()

            pay_record = PayRecord(
                emp_id=person.emp_id,
                salary=float(str(row['salary']).replace(',', '')),
                gross_total=float(str(row['gross_total']).replace(',', '')),
                period_end=period_end,
                # Ensure raw_json is stored as a string, only if column exists
                raw_json=row.get('raw_json') if 'raw_json' in df.columns and pd.notna(row.get('raw_json')) else None 
            )
            db.add(pay_record)
        db.commit()
        print(f"Successfully populated {len(df)} pay records from {file_path}")
    except Exception as e:
        db.rollback()
        print(f"Error populating pay records from {file_path}: {e}")
    finally:
        db.close()

def populate_organisations_from_csv(file_path: str):
    """Populates the organisations table from a CSV file."""
    db = SessionLocal()
    try:
        # Use cp1252 encoding to properly handle apostrophes and other special characters
        df = pd.read_csv(file_path, encoding='cp1252')

        for index, row in df.iterrows():
            # Check if organisation already exists by institution and branch (or just institution if branch is null)
            existing_org = db.query(Organisation).filter(
                Organisation.institution == row['institution'],
                Organisation.branch == (row['branch'] if pd.notna(row['branch']) else None)
            ).first()

            if existing_org:
                print(f"Organisation {row['institution']} branch {row['branch']} already exists. Skipping.")
                continue

            organisation = Organisation(
                type=row['type'],
                manager=row['manager'] if pd.notna(row['manager']) else None,
                institution=row['institution'],
                branch=row['branch'] if pd.notna(row['branch']) else None,
                address1=row['address1'] if pd.notna(row['address1']) else None,
                address2=row['address2'] if pd.notna(row['address2']) else None,
                address3=row['address3'] if pd.notna(row['address3']) else None,
                city=row['city'] if pd.notna(row['city']) else None,
            )
            db.add(organisation)
        db.commit()
        print(f"Successfully populated {len(df)} organisations from {file_path}")
    except Exception as e:
        db.rollback()
        print(f"Error populating organisations from {file_path}: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    # Ensure tables are created before populating data
    create_tables()

    # --- PLACE YOUR CSV FILE PATHS HERE ---
    # Since the CSV files are in the same directory as this script,
    # you can just use their filenames directly.
    PERSONS_CSV_FILE = "persons.csv"         # <--- Your Persons CSV filename
    PAY_RECORDS_CSV_FILE = "pay_records.csv" # <--- Your Pay Records CSV filename
    #ORGANISATIONS_CSV_FILE = "organisations.csv" # <--- Your Organisations CSV filename
    # ------------------------------------

    print("\nPopulating Persons...")
    populate_persons_from_csv(PERSONS_CSV_FILE)

    print("\nPopulating Pay Records...")
    populate_pay_records_from_csv(PAY_RECORDS_CSV_FILE)

    #print("\nPopulating Organisations...")
    #populate_organisations_from_csv(ORGANISATIONS_CSV_FILE)

    print("\nDatabase population complete!")

    # Optional: Verify data by querying
    db = SessionLocal()
    try:
        print("\nVerifying data:")
        print(f"Total persons: {db.query(Person).count()}")
        print(f"Total pay records: {db.query(PayRecord).count()}")
        #print(f"Total organisations: {db.query(Organisation).count()}")

        first_person = db.query(Person).first()
        if first_person:
            print(f"\nFirst person: {first_person.full_name}, Rank: {first_person.rank}")
            for pr in first_person.pay_records:
                print(f"  - Pay record for {pr.period_end}: Gross Total {pr.gross_total}")

    except Exception as e:
        print(f"Error verifying data: {e}")
    finally:
        db.close()