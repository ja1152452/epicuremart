content = open('app.py', encoding='utf-8').read()

old = "    return send_file(pdf_buffer, mimetype='application/pdf', as_attachment=False, download_name=filename)\n\n\n@app.route('/seller/shop/create'"

new = """    from flask import make_response
    response = make_response(pdf_buffer.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'inline; filename=\"{filename}\"'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    return response


@app.route('/seller/shop/create'"""

if old in content:
    content = content.replace(old, new, 1)
    open('app.py', 'w', encoding='utf-8').write(content)
    print('replaced')
else:
    print('not found')
