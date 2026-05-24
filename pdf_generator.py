"""
Enhanced PDF Report Generator for Epicuremart
Generates formal, structured sales reports with charts and tables
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.charts.barcharts import VerticalBarChart
from datetime import datetime
import io


def generate_admin_sales_report_pdf(start_date=None, end_date=None, orders_data=None, stats=None):
    """Generate comprehensive admin sales report PDF"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
    elements = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=24, textColor=colors.HexColor('#1a1a1a'), 
                                  spaceAfter=10, alignment=TA_CENTER, fontName='Helvetica-Bold')
    subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#666666'),
                                     spaceAfter=20, alignment=TA_CENTER)
    heading_style = ParagraphStyle('Heading', parent=styles['Heading2'], fontSize=14, textColor=colors.HexColor('#2c3e50'),
                                    spaceAfter=12, spaceBefore=20, fontName='Helvetica-Bold')
    
    # Header
    elements.append(Paragraph("EPICUREMART", title_style))
    elements.append(Paragraph("Admin Sales Report", subtitle_style))
    
    # Report Info
    date_range = f"{start_date.strftime('%B %d, %Y')} - {end_date.strftime('%B %d, %Y')}" if start_date and end_date else "All Time"
    info_data = [
        ['Report Generated:', datetime.now().strftime('%B %d, %Y %I:%M %p')],
        ['Period:', date_range],
        ['Report Type:', 'Administrative Sales Summary']
    ]
    info_table = Table(info_data, colWidths=[2*inch, 4*inch])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#555555')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 20))
    
    # Executive Summary
    elements.append(Paragraph("EXECUTIVE SUMMARY", heading_style))
    summary_data = [
        ['Metric', 'Value'],
        ['Total Orders', f"{stats.get('total_orders', 0):,}"],
        ['Total Revenue', f"₱{float(stats.get('total_revenue', 0)):,.2f}"],
        ['Platform Commission (5%)', f"₱{float(stats.get('commission_received', 0)):,.2f}"],
        ['Seller Earnings (95%)', f"₱{float(stats.get('seller_earnings', 0)):,.2f}"],
        ['Average Order Value', f"₱{float(stats.get('avg_order_value', 0)):,.2f}"],
    ]
    summary_table = Table(summary_data, colWidths=[3*inch, 2.5*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#ecf0f1')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bdc3c7')),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 20))
    
    # Order Status Breakdown
    if stats.get('orders_by_status'):
        elements.append(Paragraph("ORDER STATUS BREAKDOWN", heading_style))
        status_data = [['Status', 'Count', 'Percentage']]
        total = stats.get('total_orders', 1)
        for status, count in stats.get('orders_by_status', []):
            pct = (count / total * 100) if total > 0 else 0
            status_data.append([status.replace('_', ' ').title(), str(count), f"{pct:.1f}%"])
        
        status_table = Table(status_data, colWidths=[2.5*inch, 1.5*inch, 1.5*inch])
        status_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(status_table)
        elements.append(Spacer(1, 20))
    
    # Top Products
    if stats.get('top_products'):
        elements.append(Paragraph("TOP SELLING PRODUCTS", heading_style))
        products_data = [['Rank', 'Product Name', 'Units Sold']]
        for idx, (name, sold) in enumerate(stats.get('top_products', [])[:10], 1):
            products_data.append([str(idx), name[:40], str(int(sold))])
        
        products_table = Table(products_data, colWidths=[0.8*inch, 3.5*inch, 1.2*inch])
        products_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#27ae60')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (2, 0), (2, -1), 'CENTER'),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(products_table)
        elements.append(Spacer(1, 20))
    
    # Detailed Transactions (if provided)
    if orders_data and len(orders_data) > 0:
        elements.append(PageBreak())
        elements.append(Paragraph("DETAILED TRANSACTIONS", heading_style))
        
        trans_data = [['Order #', 'Date', 'Shop', 'Amount', 'Commission', 'Status']]
        for order in orders_data[:50]:  # Limit to 50 for PDF size
            trans_data.append([
                order.order_number[:15],
                order.created_at.strftime('%m/%d/%y'),
                order.shop.name[:20] if order.shop else 'N/A',
                f"₱{float(order.total_amount):,.2f}",
                f"₱{float(order.commission_amount):,.2f}",
                order.status[:12]
            ])
        
        trans_table = Table(trans_data, colWidths=[1.2*inch, 0.8*inch, 1.5*inch, 1*inch, 1*inch, 1*inch])
        trans_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e74c3c')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(trans_table)
        
        if len(orders_data) > 50:
            elements.append(Spacer(1, 10))
            elements.append(Paragraph(f"<i>Showing 50 of {len(orders_data)} transactions. View full report in dashboard.</i>", 
                                    ParagraphStyle('Note', parent=styles['Normal'], fontSize=8, textColor=colors.grey)))
    
    # Footer
    elements.append(Spacer(1, 30))
    footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.grey, alignment=TA_CENTER)
    elements.append(Paragraph("This is a system-generated report. For inquiries, contact admin@epicuremart.com", footer_style))
    
    doc.build(elements)
    buffer.seek(0)
    return buffer
