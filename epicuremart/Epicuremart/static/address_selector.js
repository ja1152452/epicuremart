/**
 * CALABARZON Address Selector
 * Handles cascading dropdowns for Province → Municipality → Barangay → Postal Code
 */

// Initialize address selector
function initializeAddressSelector(provinceSelectId, municipalitySelectId, barangaySelectId, postalCodeInputId) {
    const provinceSelect = document.getElementById(provinceSelectId);
    const municipalitySelect = document.getElementById(municipalitySelectId);
    const barangaySelect = document.getElementById(barangaySelectId);
    const postalCodeInput = document.getElementById(postalCodeInputId);
    
    if (!provinceSelect || !municipalitySelect || !barangaySelect || !postalCodeInput) {
        console.error('Address selector elements not found');
        return;
    }
    
    // Load provinces on page load
    loadProvinces(provinceSelect);
    
    // Province change event
    provinceSelect.addEventListener('change', function() {
        const province = this.value;
        clearSelect(municipalitySelect, 'Select Municipality/City');
        clearSelect(barangaySelect, 'Select Barangay');
        postalCodeInput.value = '';
        
        if (province && CALABARZON_DATA[province]) {
            loadMunicipalities(municipalitySelect, province);
            municipalitySelect.disabled = false;
        } else {
            municipalitySelect.disabled = true;
            barangaySelect.disabled = true;
        }
    });
    
    // Municipality change event
    municipalitySelect.addEventListener('change', function() {
        const province = provinceSelect.value;
        const municipality = this.value;
        clearSelect(barangaySelect, 'Select Barangay');
        postalCodeInput.value = '';
        
        if (province && municipality && CALABARZON_DATA[province][municipality]) {
            loadBarangays(barangaySelect, province, municipality);
            autoFillPostalCode(postalCodeInput, province, municipality);
            barangaySelect.disabled = false;
        } else {
            barangaySelect.disabled = true;
        }
    });
}

// Load provinces into dropdown
function loadProvinces(selectElement) {
    clearSelect(selectElement, 'Select Province');
    
    for (const province in CALABARZON_DATA) {
        const option = document.createElement('option');
        option.value = province;
        option.textContent = province;
        selectElement.appendChild(option);
    }
}

// Load municipalities for selected province
function loadMunicipalities(selectElement, province) {
    clearSelect(selectElement, 'Select Municipality/City');
    
    if (!CALABARZON_DATA[province]) return;
    
    const municipalities = Object.keys(CALABARZON_DATA[province]).sort();
    municipalities.forEach(municipality => {
        const option = document.createElement('option');
        option.value = municipality;
        option.textContent = municipality;
        selectElement.appendChild(option);
    });
}

// Load barangays for selected municipality
function loadBarangays(selectElement, province, municipality) {
    clearSelect(selectElement, 'Select Barangay');
    
    if (!CALABARZON_DATA[province] || !CALABARZON_DATA[province][municipality]) return;
    
    const barangays = CALABARZON_DATA[province][municipality].barangays.sort();
    barangays.forEach(barangay => {
        const option = document.createElement('option');
        option.value = barangay;
        option.textContent = barangay;
        selectElement.appendChild(option);
    });
}

// Auto-fill postal code based on municipality
function autoFillPostalCode(inputElement, province, municipality) {
    if (!CALABARZON_DATA[province] || !CALABARZON_DATA[province][municipality]) return;
    
    const postalCode = CALABARZON_DATA[province][municipality].postal_code;
    inputElement.value = postalCode;
}

// Clear select dropdown
function clearSelect(selectElement, placeholder) {
    selectElement.innerHTML = '';
    const defaultOption = document.createElement('option');
    defaultOption.value = '';
    defaultOption.textContent = placeholder;
    selectElement.appendChild(defaultOption);
}

// Validate address selection
function validateAddressSelection(provinceSelectId, municipalitySelectId, barangaySelectId, postalCodeInputId) {
    const province = document.getElementById(provinceSelectId).value;
    const municipality = document.getElementById(municipalitySelectId).value;
    const barangay = document.getElementById(barangaySelectId).value;
    const postalCode = document.getElementById(postalCodeInputId).value;
    
    if (!province || !municipality || !barangay || !postalCode) {
        return {
            valid: false,
            message: 'Please complete all address fields'
        };
    }
    
    return {
        valid: true,
        address: {
            province: province,
            municipality: municipality,
            barangay: barangay,
            postal_code: postalCode
        }
    };
}
