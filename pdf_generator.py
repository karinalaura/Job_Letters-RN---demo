# -*- coding: utf-8 -*-
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Paragraph, Frame
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_CENTER
import os
from PIL import Image

def create_job_letter_pdf(employee_data, org_details, current_date, flash_key):
    """
    Create a job letter PDF using ReportLab with proper background image and verification flash key
    """
    from io import BytesIO
    
    # Create a BytesIO buffer to hold the PDF
    buffer = BytesIO()
    
    # Create the PDF canvas with metadata
    p = canvas.Canvas(buffer, pagesize=A4)
    
    # Set PDF document info immediately
    p.setTitle("Job Letter")
    p.setAuthor("Job Letter Generator")
    p.setSubject("Employment Verification Letter")
    p.setCreator("Job Letter Generator")
    
    width, height = A4
    
    # ===== STYLES CONFIGURATION =====
    styles = getSampleStyleSheet()
    
    # Base style configuration
    base_font_size = 12
    line_spacing = 18  # 1.5 * 12pt = 18pt for 1.5 line spacing
    
    # Document styles
    document_styles = {
        'normal': ParagraphStyle(
            'Normal',
            parent=styles['Normal'],
            fontName='Times-Roman',
            fontSize=base_font_size,
            leading=line_spacing,
            alignment=TA_JUSTIFY,
            spaceAfter=6
        ),
        'header': ParagraphStyle(
            'Header',
            parent=styles['Normal'],
            fontName='Times-Bold',
            fontSize=base_font_size,
            leading=line_spacing,
            alignment=TA_LEFT,
            spaceAfter=4
        )
    }
    
    # Layout configuration
    layout_config = {
        'left_margin': 75,
        'right_margin': 75,
        'letterhead_height': 150,
        'content_start_offset': 200,
        'section_spacing': {
            'ref_to_date': 30,
            'date_to_address': 30,
            'address_line_spacing': 15,
            'address_to_salutation': 20,
            'salutation_to_body': 20,
            'between_paragraphs': 10,
            'body_to_closing': 30,
            'closing_to_signature': 60
        }
    }
    
    # ===== BACKGROUND AND LETTERHEAD SETUP =====
    # Add the background watermark image
    watermark_path = os.path.join(os.path.dirname(__file__), 'static', 'watermark.png')
    if os.path.exists(watermark_path):
        p.drawImage(watermark_path, 0, 0, width=width, height=height, preserveAspectRatio=True, mask='auto')
    
    # Calculate content dimensions
    content_width = width - layout_config['left_margin'] - layout_config['right_margin']
    content_start_y = height - layout_config['content_start_offset']
    
    # Add the letterhead image at the top
    letterhead_path = os.path.join(os.path.dirname(__file__), 'static', 'letterhead.png')
    if os.path.exists(letterhead_path):
        letterhead_x = layout_config['left_margin']
        letterhead_y = height - 30 - layout_config['letterhead_height']
        p.drawImage(letterhead_path, letterhead_x, letterhead_y, 
                   width=content_width, height=layout_config['letterhead_height'], 
                   preserveAspectRatio=True, mask='auto')
    
    # ===== CONTENT GENERATION =====
    # Reference number (bold)
    badge_number = '[Badge Number]'  # Default value
    if employee_data and not employee_data.get('error'):
        # Handle different possible data types for badge
        badge_value = employee_data.get('badge')
        if badge_value is not None:
            # Convert to string and strip whitespace
            badge_str = str(badge_value).strip()
            if badge_str:  # Check if not empty after stripping
                badge_number = badge_str
    
    ref_text = f"<b>PF: {badge_number}</b>"
    ref_para = Paragraph(ref_text, document_styles['normal'])
    ref_para.wrap(content_width, 50)
    ref_para.drawOn(p, layout_config['left_margin'], content_start_y - ref_para.height)
    
    # Date (bold)
    date_y = content_start_y - layout_config['section_spacing']['ref_to_date']
    date_text = f"<b>{current_date}</b>"
    date_para = Paragraph(date_text, document_styles['normal'])
    date_para.wrap(content_width, 50)
    date_para.drawOn(p, layout_config['left_margin'], date_y - date_para.height)
    
    # Recipient address (bold)
    address_y = date_y - layout_config['section_spacing']['date_to_address']
    if org_details and not org_details.get('error'):
        address_lines = []
        if org_details.get('manager'): address_lines.append(f"<b>{org_details['manager']}</b>")
        if org_details.get('institution'): address_lines.append(f"<b>{org_details['institution']}</b>")
        if org_details.get('address1'): address_lines.append(f"<b>{org_details['address1']}</b>")
        if org_details.get('address2'): address_lines.append(f"<b>{org_details['address2']}</b>")
        if org_details.get('address3'): address_lines.append(f"<b>{org_details['address3']}</b>")
        if org_details.get('city'): address_lines.append(f"<b>{org_details['city']}</b>")
    else:
        address_lines = ['<b>[Institution Name]</b>', '<b>[Address Line 1]</b>', '<b>[Address Line 2]</b>', '<b>[Address Line 3]</b>', '<b>[City]</b>']
    
    # Draw address lines using Paragraph objects for bold formatting
    current_address_y = address_y
    for line in address_lines:
        addr_para = Paragraph(line, document_styles['normal'])
        addr_para.wrap(content_width, 50)
        addr_para.drawOn(p, layout_config['left_margin'], current_address_y - addr_para.height)
        current_address_y -= layout_config['section_spacing']['address_line_spacing']
    
    # Salutation (Times New Roman)
    salutation_y = current_address_y - layout_config['section_spacing']['address_to_salutation']
    salutation_para = Paragraph("Dear Sir/Madam,", document_styles['normal'])
    salutation_para.wrap(content_width, 50)
    salutation_para.drawOn(p, layout_config['left_margin'], salutation_y - salutation_para.height)
    
    # Letter body paragraphs
    body_y = salutation_y - salutation_para.height - layout_config['section_spacing']['salutation_to_body']
    
    # Paragraph 1 - Use same safe extraction as reference number
    if employee_data and not employee_data.get('error'):
        full_name = employee_data.get('full_name', '[Employee Full Name]')
        # Use same logic as reference number for consistency  
        badge_value = employee_data.get('badge')
        if badge_value is not None:
            badge = str(badge_value).strip() if str(badge_value).strip() else '[Badge Number]'
        else:
            badge = '[Badge Number]'
        engagement_date = employee_data.get('engagement_date', '[Engagement Date]')
        
        para1_text = f"This serves to inform that <b>{full_name} <i>(Regimental Number {badge})</i></b> enlisted as a member of the Trinidad and Tobago Police Service with effect from {engagement_date}."
    else:
        para1_text = "This serves to inform that <b>[Employee Full Name] <i>(Regimental Number [Badge Number])</i></b> enlisted as a member of the Trinidad and Tobago Police Service with effect from [Engagement Date]."
    
    para1 = Paragraph(para1_text, document_styles['normal'])
    para1.wrap(content_width, 100)
    para1.drawOn(p, layout_config['left_margin'], body_y - para1.height)
    
    # Paragraph 2 - Rank information
    para2_y = body_y - para1.height - layout_config['section_spacing']['between_paragraphs']
    if employee_data and not employee_data.get('error'):
        rank = employee_data.get('rank', '[Employee Rank]')
        acting_rank = employee_data.get('acting_rank')
        
        if acting_rank and acting_rank not in ['N/A', '']:
            para2_text = f"At present, the officer holds the substantive rank of <b>{rank}</b>. However, this officer is currently acting in the next higher rank as <b>{acting_rank}</b>."
        else:
            para2_text = f"At present, the officer holds the substantive rank of <b>{rank}</b>."
    else:
        para2_text = "At present, the officer holds the substantive rank of <b>[Employee Rank]</b>."
    
    para2 = Paragraph(para2_text, document_styles['normal'])
    para2.wrap(content_width, 100)
    para2.drawOn(p, layout_config['left_margin'], para2_y - para2.height)
    
    # Paragraph 3 - Salary information
    para3_y = para2_y - para2.height - layout_config['section_spacing']['between_paragraphs']
    if employee_data and not employee_data.get('error'):
        full_name = employee_data.get('full_name', '[Employee Full Name]')
        total_gross_words = employee_data.get('total_gross_words', '[Total Gross in Words]')
        total_gross = employee_data.get('total_gross', 0.00)
        
        para3_text = f"{full_name} is in receipt of a monthly remuneration of <b><i>{total_gross_words} (${total_gross:.2f})</i> inclusive of allowances which are subject to Departmental Deductions.</b> <i>(Salary Statement Attached)</i>"
    else:
        para3_text = "[Employee Full Name] is in receipt of a monthly remuneration of <b><i>[Total Gross in Words] ($0.00)</i) inclusive of allowances which are subject to Departmental Deductions.</b> <i>(Salary Statement Attached)</i>"
    
    para3 = Paragraph(para3_text, document_styles['normal'])
    para3.wrap(content_width, 100)
    para3.drawOn(p, layout_config['left_margin'], para3_y - para3.height)
    
    # Closing (Times New Roman)
    closing_y = para3_y - para3.height - layout_config['section_spacing']['body_to_closing']
    
    # "Yours faithfully," text
    faithfully_text = "Yours faithfully,"
    faithfully_para = Paragraph(faithfully_text, document_styles['normal'])
    faithfully_para.wrap(content_width, 100)
    faithfully_para.drawOn(p, layout_config['left_margin'], closing_y - faithfully_para.height)
    
    # Add signature image - choose based on badge number
    sig_y = closing_y - faithfully_para.height - 10  # Added 10 points spacing to lower signature
    try:
        # Determine which signature to use based on badge number
        badge_number = employee_data.get('badge', '')
        if badge_number == '13868':
            sig_filename = 'sig2.png'
        else:
            sig_filename = 'mainsig.png'
        
        sig_path = os.path.join(os.path.dirname(__file__), 'static', sig_filename)
        if os.path.exists(sig_path):
            sig_img = ImageReader(sig_path)
            # Adjust signature size as needed (width, height in points)
            sig_width = 150
            sig_height = 40
            p.drawImage(sig_img, layout_config['left_margin'], sig_y - sig_height, 
                       width=sig_width, height=sig_height, preserveAspectRatio=True, mask='auto')
            commissioner_y = sig_y - sig_height
        else:
            print(f"Warning: Signature image not found at {sig_path}")
            commissioner_y = sig_y
    except Exception as e:
        print(f"Error loading signature image: {e}")
        commissioner_y = sig_y
    
    # "Commissioner of Police" text below signature
    commissioner_text = """/f/ Commissioner of Police"""
    commissioner_para = Paragraph(commissioner_text, document_styles['normal'])
    commissioner_para.wrap(content_width, 100)
    commissioner_para.drawOn(p, layout_config['left_margin'], commissioner_y - commissioner_para.height)
    
    # Finalize the PDF
    p.showPage()
    p.save()
    
    # Get the PDF data
    pdf_data = buffer.getvalue()
    buffer.close()
    
    return pdf_data