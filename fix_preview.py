content = open('app.py', encoding='utf-8').read()

# Find and replace the seller export route to add a separate inline viewer route
old = "@app.route('/seller/sales-report/export-pdf')"

new = """@app.route('/seller/sales-report/preview-pdf')
@login_required
@role_required('seller')
def seller_sales_report_preview_pdf():
    \"\"\"Return PDF as base64 JSON for modal preview\"\"\"
    import base64
    user = User.query.get(session['user_id'])
    if not user.shop:
        return jsonify({'error': 'No shop'}), 400
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    start_date = None
    end_date = None
    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        except ValueError:
            pass
    pdf_buffer = generate_sales_report_pdf('seller', session['user_id'], start_date, end_date)
    if not pdf_buffer:
        return jsonify({'error': 'Failed'}), 500
    pdf_b64 = base64.b64encode(pdf_buffer.read()).decode('utf-8')
    return jsonify({'pdf': pdf_b64})


@app.route('/seller/sales-report/export-pdf')"""

if old in content:
    content = content.replace(old, new, 1)
    open('app.py', 'w', encoding='utf-8').write(content)
    print('done')
else:
    print('not found')
