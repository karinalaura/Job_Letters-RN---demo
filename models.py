from sqlalchemy import create_engine, Column, Integer, String, Date, DateTime, Numeric, Text, ForeignKey, func
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from flask_login import UserMixin
import datetime

# Base class for declarative models
Base = declarative_base()

class Person(Base, UserMixin):
    __tablename__ = "persons"
    emp_id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, index=True, nullable=False)
    nis = Column(Integer, unique=True, nullable=True)      # Primary login identifier (NIS number)
    badge_number = Column(String, unique=True, index=True, nullable=False) # Actual employee badge number/ID                 # From original "RN 67890", often maps to badge_number or another internal ID
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    rank = Column(String, nullable=False)
    acting_rank = Column(String, nullable=True)
    department = Column(String, nullable=True)
    enlistment_date = Column(Date, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    # New fields for one-time code authentication, now on Person table
    one_time_code = Column(String, nullable=True)
    one_time_code_expires_at = Column(DateTime, nullable=True)

    pay_records = relationship("PayRecord", back_populates="person", cascade="all, delete-orphan")

class PayRecord(Base):
    __tablename__ = "pay_records"
    id = Column(Integer, primary_key=True, index=True)
    emp_id = Column(Integer, ForeignKey("persons.emp_id", ondelete="CASCADE"), nullable=False, index=True)
    salary = Column(Numeric(12,2), nullable=False)
    gross_total = Column(Numeric(12,2), nullable=True)
    period_end = Column(Date, nullable=True)
    
    raw_json = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    person = relationship("Person", back_populates="pay_records")

class Organisation(Base):
    __tablename__ = "organisations"
    id = Column(Integer, primary_key=True, index=True)
    type = Column(String, nullable=False)
    manager = Column(String, nullable=True)
    institution = Column(String, nullable=False)
    branch = Column(String, nullable=True)
    address1 = Column(String, nullable=True)
    address2 = Column(String, nullable=True)
    address3 = Column(String, nullable=True)
    city = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

class FlashKey(Base):
    __tablename__ = "flash_keys"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True)
    pdf_id = Column(Integer, ForeignKey("generated_pdfs.id", ondelete="CASCADE"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.now)
    
    generated_pdf = relationship("GeneratedPDF")

    
class GeneratedPDF(Base):
    __tablename__ = "generated_pdfs"
    id = Column(Integer, primary_key=True, index=True)
    emp_id = Column(Integer, ForeignKey("persons.emp_id"), nullable=False, index=True)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    organization_name = Column(String, nullable=True)
    generated_at = Column(DateTime, default=datetime.datetime.now)
    
    # Verification columns for QR code generation
    employee_badge_number = Column(String, nullable=True)  # Badge number at time of generation
    employee_full_name = Column(String, nullable=True)     # Full name at time of generation
    employee_rank = Column(String, nullable=True)          # Rank at time of generation
    employee_acting_rank = Column(String, nullable=True)   # Acting rank at time of generation
    employee_engagement_date = Column(Date, nullable=True) # Engagement date at time of generation
    employee_gross_salary = Column(Numeric(12,2), nullable=True)  # Gross salary at time of generation
    
    person = relationship("Person")