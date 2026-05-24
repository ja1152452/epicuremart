import io

path = r'app.py'
with io.open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f'Total lines: {len(lines)}')

# Find start and end of old delivery fee routes
start_idx = None
end_idx = None
for i, line in enumerate(lines):
    if "@app.route('/admin/delivery-fees')" in line and start_idx is None:
        start_idx = i
    if '# ==================== API ROUTES FOR QR SCANNING ====================' in line:
        end_idx = i
        break

print(f'Start: {start_idx}, End: {end_idx}')
if start_idx is None or end_idx is None:
    print('MARKERS NOT FOUND')
    exit(1)

new_routes = """@app.route('/admin/delivery-fees')
@login_required
@role_required('admin')
def admin_delivery_fees():
    base_fee = app.config.get('DELIVERY_BASE_FEE', 50.0)
    inter_island_fee = app.config.get('DELIVERY_INTER_ISLAND_FEE', 30.0)
    return render_template('admin_delivery_fees.html',
        base_fee=base_fee,
        inter_island_fee=inter_island_fee
    )


@app.route('/admin/delivery-fees/update', methods=['POST'])
@login_required
@role_required('admin')
def admin_update_delivery_fees():
    import json
    base_fee = float(request.form.get('base_fee', 50.0))
    inter_island_fee = float(request.form.get('inter_island_fee', 30.0))
    app.config['DELIVERY_BASE_FEE'] = base_fee
    app.config['DELIVERY_INTER_ISLAND_FEE'] = inter_island_fee
    config_path = os.path.join(os.path.dirname(__file__), 'delivery_config.json')
    with open(config_path, 'w') as f:
        json.dump({'base_fee': base_fee, 'inter_island_fee': inter_island_fee}, f)
    log_action('DELIVERY_FEES_UPDATED', 'Config', None, 'Rates updated')
    flash('Delivery fee rates updated successfully.', 'success')
    return redirect(url_for('admin_delivery_fees'))


"""

result = lines[:start_idx] + [new_routes] + lines[end_idx:]
with io.open(path, 'w', encoding='utf-8') as f:
    f.writelines(result)
print(f'SUCCESS, new total: {len(result)}')
