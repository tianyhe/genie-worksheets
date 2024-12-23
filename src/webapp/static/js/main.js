// Constants
const PREDEFINED_TYPES = ['str', 'int', 'float', 'bool', 'date', 'time', 'Enum', "confirm"];
const BOOLEAN_COLUMNS = [10, 11, 12]; // Don't Ask, Required, Field Confirmation
const KIND_TYPES = ['WS', 'DB', 'Type'];
const FIELD_KIND_TYPES = ['input', 'internal', 'output'];

// DOM Elements
let spreadsheet;
let sheetBody;
let addFieldBtn;
let activeTooltip = null;
let currentTaskRow = null;

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    spreadsheet = document.getElementById('spreadsheet');
    sheetBody = document.getElementById('sheet-body');
    addFieldBtn = document.getElementById('addField');

    initializeEventListeners();
    initializeTooltips();

    // Initialize code editor modal
    codeEditorModal = createCodeEditorModal();
    
    // Add click handler for code cells and edit buttons
    document.addEventListener('click', (e) => {
        if (e.target.closest('.btn-edit-code')) {
            const cell = e.target.closest('.code-cell-wrapper').querySelector('.cell-input');
            codeEditorModal.show(cell);
            e.preventDefault();
            e.stopPropagation();
        }
    });
    
    document.addEventListener('dblclick', (e) => {
        const element = e.target;
        if (element.classList.contains('cell-input') && 
            (element.classList.contains('predicate-input') || 
             element.classList.contains('action-input') || 
             Array.from(element.closest('td').parentNode.children).indexOf(element.closest('td')) === 13)) {
            codeEditorModal.show(element);
        }
    });

    // Add input handler for code cells to sync with CodeMirror
    document.addEventListener('input', (e) => {
        const element = e.target;
        if (element.classList.contains('cell-input') && 
            (element.classList.contains('predicate-input') || 
             element.classList.contains('action-input') || 
             Array.from(element.closest('td').parentNode.children).indexOf(element.closest('td')) === 13)) {
            element.setAttribute('data-original-code', element.value);
        }
    });

    // Add context menu handler
    sheetBody.addEventListener('contextmenu', (e) => {
        const row = e.target.closest('tr');
        if (row && !row.classList.contains('enum-field')) {
            e.preventDefault();
            createContextMenu(e.pageX, e.pageY, row);
        }
    });
    
    // Remove context menu when clicking outside
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.context-menu')) {
            removeContextMenu();
        }
    });
    
    // Remove context menu when scrolling
    document.addEventListener('scroll', removeContextMenu);
});

// Initialize tooltips
function initializeTooltips() {
    const tooltipContainer = document.createElement('div');
    tooltipContainer.className = 'tooltip-container';
    document.body.appendChild(tooltipContainer);

    document.querySelectorAll('.column-header').forEach(header => {
        header.addEventListener('mouseenter', (e) => {
            const tooltip = header.getAttribute('data-tooltip');
            if (tooltip) {
                const rect = header.getBoundingClientRect();
                const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;
                const scrollTop = window.pageYOffset || document.documentElement.scrollTop;

                tooltipContainer.innerHTML = `
                    <div class="tooltip-content">
                        ${tooltip}
                        <div class="tooltip-arrow"></div>
                    </div>
                `;

                tooltipContainer.style.display = 'block';
                const tooltipContent = tooltipContainer.querySelector('.tooltip-content');
                
                // Position the tooltip
                const tooltipRect = tooltipContent.getBoundingClientRect();
                const left = rect.left + (rect.width / 2) - (tooltipRect.width / 2) + scrollLeft;
                const top = rect.top - tooltipRect.height - 10 + scrollTop;

                tooltipContent.style.left = `${left}px`;
                tooltipContent.style.top = `${top}px`;
            }
        });

        header.addEventListener('mouseleave', () => {
            tooltipContainer.style.display = 'none';
        });
    });
}

// Event Listeners
function initializeEventListeners() {
    document.getElementById('addTask').addEventListener('click', () => {
        addNewRow('task');
        addFieldBtn.disabled = false;
        currentTaskRow = sheetBody.lastElementChild;
    });

    document.getElementById('addField').addEventListener('click', () => {
        if (currentTaskRow) {
            addNewRow('field');
        }
    });

    document.getElementById('processSheet').addEventListener('click', handleProcessSheet);

    document.getElementById('resetSheet').addEventListener('click', () => {
        if (confirm('Are you sure you want to reset the sheet? This will delete all tasks and fields.')) {
            sheetBody.innerHTML = '';
            addFieldBtn.disabled = false;
            currentTaskRow = sheetBody.lastElementChild;
        }
    });

    document.getElementById('downloadJson').addEventListener('click', () => {
        const sheetData = getSheetData();
        const jsonString = JSON.stringify(sheetData, null, 2);
        const blob = new Blob([jsonString], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'spreadsheet_data.json';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    });

    // Remove tooltip when clicking outside
    document.addEventListener('click', (e) => {
        if (!e.target.classList.contains('cell-input')) {
            removeTooltip();
        }
    });

    // Basic validation
    sheetBody.addEventListener('input', handleInputValidation);

    // Add click handler for code cells
    document.addEventListener('dblclick', (e) => {
        const element = e.target;
        if (element.classList.contains('cell-input')) {
            const columnIndex = Array.from(element.closest('td').parentNode.children).indexOf(element.closest('td'));
            if (element.classList.contains('predicate-input') || 
                element.classList.contains('action-input') || 
                columnIndex === 13) { // Field validation column
                codeEditorModal.show(element);
            }
        }
    });
}

// Row Creation Functions
function createTypeSelect() {
    const wrapper = document.createElement('div');
    wrapper.className = 'type-select-wrapper';
    
    // Create combobox container
    const combobox = document.createElement('div');
    combobox.className = 'combobox';
    
    // Create editable input
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'cell-input type-input';
    input.setAttribute('list', 'type-options');
    input.placeholder = 'Select or enter type';
    
    // Create datalist for suggestions
    const dataList = document.createElement('datalist');
    dataList.id = 'type-options';
    
    // Add predefined types to datalist
    PREDEFINED_TYPES.forEach(type => {
        const option = document.createElement('option');
        option.value = type;
        dataList.appendChild(option);
    });
    
    // Add event listeners
    input.addEventListener('input', (e) => {
        input.classList.remove('validation-error');
        removeTooltip();
    });
    
    input.addEventListener('blur', (e) => {
        if (!input.value.trim()) {
            input.value = PREDEFINED_TYPES[0];
        }
    });
    
    combobox.appendChild(input);
    combobox.appendChild(dataList);
    wrapper.appendChild(combobox);
    
    return wrapper;
}

function createKindSelect(isField = false) {
    const select = document.createElement('select');
    select.className = 'cell-input';
    const types = isField ? FIELD_KIND_TYPES : KIND_TYPES;
    types.forEach(type => {
        const option = document.createElement('option');
        option.value = type.toLowerCase();
        option.textContent = type;
        select.appendChild(option);
    });
    return select;
}

function createToggle(title) {
    const div = document.createElement('div');
    div.className = 'form-check';
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.className = 'form-check-input';
    input.title = title;
    div.appendChild(input);
    return div;
}

// Row Management Functions
function addNewRow(type, referenceRow = null, position = 'after') {
    const row = document.createElement('tr');
    row.className = type + '-row';
    
    // Calculate row number based on position
    let rowNum;
    if (referenceRow) {
        const visibleRows = Array.from(sheetBody.children).filter(r => !r.classList.contains('enum-field'));
        const refIndex = visibleRows.indexOf(referenceRow);
        rowNum = refIndex + (position === 'after' ? 2 : 1);
    } else {
        rowNum = sheetBody.children.length + 1;
    }
    
    row.innerHTML = `
        <td>${rowNum}</td>
        <td>${type.charAt(0).toUpperCase() + type.slice(1)}</td>
    `;

    if (type === 'task') {
        addTaskCells(row);
        currentTaskRow = row;
        addFieldBtn.disabled = false;
    } else {
        // For fields, find the parent task row
        let taskRow = referenceRow;
        while (taskRow && !taskRow.classList.contains('task-row')) {
            taskRow = taskRow.previousElementSibling;
        }
        if (taskRow) {
            currentTaskRow = taskRow;
            addFieldBtn.disabled = false;
            addFieldCells(row);
        } else {
            // If no task row found, convert this to a task row
            row.className = 'task-row';
            addTaskCells(row);
            currentTaskRow = row;
            addFieldBtn.disabled = false;
        }
    }

    addDeleteButton(row, type);

    // Insert the row at the correct position
    if (referenceRow) {
        if (position === 'before') {
            referenceRow.parentNode.insertBefore(row, referenceRow);
        } else {
            // For 'after', insert after any enum rows
            let insertPoint = referenceRow;
            while (insertPoint.nextElementSibling && insertPoint.nextElementSibling.classList.contains('enum-field')) {
                insertPoint = insertPoint.nextElementSibling;
            }
            if (insertPoint.nextElementSibling) {
                insertPoint.parentNode.insertBefore(row, insertPoint.nextElementSibling);
            } else {
                insertPoint.parentNode.appendChild(row);
            }
        }
    } else {
        sheetBody.appendChild(row);
    }

    if (type === 'field') {
        setupEnumHandling(row);
    }

    renumberRows();
    return row;
}

function addTaskCells(row) {
    const cells = [];
    
    cells.push('<td><div class="code-cell-wrapper"><textarea class="cell-input predicate-input" placeholder="Form Predicate"></textarea><button class="btn-edit-code" title="Edit code"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg></button></div></td>');
    cells.push('<td><input type="text" class="cell-input" placeholder="Form Name"></td>');
    cells.push('<td></td>');
    
    const kindCell = document.createElement('td');
    kindCell.appendChild(createKindSelect());
    cells.push(kindCell.outerHTML);
    
    cells.push('<td colspan="8"></td>');
    cells.push('<td><div class="code-cell-wrapper"><textarea class="cell-input action-input" placeholder="Form Action"></textarea><button class="btn-edit-code" title="Edit code"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg></button></div></td>');
    cells.push('<td colspan="2"></td>');
    
    row.innerHTML += cells.join('');
}

function addFieldCells(row) {
    const cells = [];
    
    // cells.push('<td><input type="text" class="cell-input" disabled></td>');
    // cells.push('<td><input type="text" class="cell-input" disabled></td>');
    cells.push('<td></td>');
    cells.push('<td></td>');
    // cells.push('<td><input type="text" class="cell-input" disabled></td>');
    cells.push('<td><div class="code-cell-wrapper"><textarea class="cell-input predicate-input" placeholder="Field Predicate"></textarea><button class="btn-edit-code" title="Edit code"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg></button></div></td>');
    
    const kindCell = document.createElement('td');
    kindCell.appendChild(createKindSelect(true));
    cells.push(kindCell.outerHTML);
    
    const typeCell = document.createElement('td');
    typeCell.appendChild(createTypeSelect());
    cells.push(typeCell.outerHTML);
    
    cells.push('<td><input type="text" class="cell-input" placeholder="Field Name"></td>');
    cells.push('<td><input type="text" class="cell-input" placeholder="Variable Enums"></td>');
    cells.push('<td><input type="text" class="cell-input" placeholder="Field Description"></td>');
    
    cells.push('<td>' + createToggle('Don\'t Ask').outerHTML + '</td>');
    cells.push('<td>' + createToggle('Required').outerHTML + '</td>');
    cells.push('<td>' + createToggle('Field Confirmation').outerHTML + '</td>');
    
    cells.push('<td><div class="code-cell-wrapper"><textarea class="cell-input action-input" placeholder="Field Action"></textarea><button class="btn-edit-code" title="Edit code"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg></button></div></td>');
    // cells.push('<td><input type="text" class="cell-input" disabled></td>');
    cells.push('<td></td>');
    cells.push('<td><div class="code-cell-wrapper"><textarea class="cell-input" placeholder="Field Validation"></textarea><button class="btn-edit-code" title="Edit code"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg></button></div></td>');
    
    row.innerHTML += cells.join('');
}

// Enum Handling Functions
function setupEnumHandling(row) {
    const typeInput = row.querySelector('.type-input');
    let enumRow = addEnumValueRow(row, false);
    
    typeInput.addEventListener('input', (e) => {
        if (e.target.value === 'Enum') {
            enableEnumRow(enumRow);
        } else {
            disableEnumRows(row, enumRow);
        }
    });
    
    // Also check on blur to handle selection from datalist
    typeInput.addEventListener('blur', (e) => {
        if (e.target.value === 'Enum') {
            enableEnumRow(enumRow);
        } else {
            disableEnumRows(row, enumRow);
        }
    });
}

function addEnumValueRow(fieldRow, enabled = false) {
    const enumRow = createEnumRow(enabled);
    insertEnumRow(enumRow, fieldRow);
    setupEnumRowHandlers(enumRow, fieldRow);
    return enumRow;
}

function createEnumRow(enabled) {
    const enumRow = document.createElement('tr');
    enumRow.className = 'enum-field';
    if (!enabled) {
        enumRow.style.display = 'none';
    }
    
    enumRow.innerHTML = `
        <td></td>
        <td colspan="7"></td>
        <td>
            <div class="enum-actions">
                <input type="text" class="cell-input enum-value" placeholder="Enum Value" ${enabled ? '' : 'disabled'}>
                <button class="btn-add-enum" title="Add another enum value" ${enabled ? '' : 'disabled'}>
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
                        <path d="M8 0a1 1 0 0 1 1 1v6h6a1 1 0 1 1 0 2H9v6a1 1 0 1 1-2 0V9H1a1 1 0 0 1 0-2h6V1a1 1 0 0 1 1-1z"/>
                    </svg>
                </button>
            </div>
        </td>
        <td colspan="7"></td>
    `;
    
    return enumRow;
}

// Utility Functions
function getEnumRows(fieldRow) {
    const enumRows = [];
    let nextRow = fieldRow.nextElementSibling;
    while (nextRow && nextRow.classList.contains('enum-field')) {
        enumRows.push(nextRow);
        nextRow = nextRow.nextElementSibling;
    }
    return enumRows;
}

function getLastEnumRow(fieldRow) {
    const enumRows = getEnumRows(fieldRow);
    return enumRows.length > 0 ? enumRows[enumRows.length - 1] : null;
}

function renumberRows() {
    const rows = sheetBody.getElementsByTagName('tr');
    let rowNum = 1;
    for (let row of rows) {
        if (!row.classList.contains('enum-field')) {
            row.cells[0].textContent = rowNum++;
        }
    }
}

// Data Processing Functions
function getSheetData() {
    const data = [];
    const rows = sheetBody.getElementsByTagName('tr');
    for (let row of rows) {
        if (row.classList.contains('enum-field')) continue;
        
        const rowData = [];
        const inputs = row.querySelectorAll('input:not(.enum-value), select');
        for (let input of inputs) {
            if (input.classList.contains('type-input')) {
                rowData.push(input.value.trim());
            } else if (input.type === 'checkbox') {
                rowData.push(input.checked ? 'TRUE' : 'FALSE');
            } else {
                rowData.push(input.value.trim());
            }
        }
        data.push(rowData);

        if (row.querySelector('.type-input')?.value === 'Enum') {
            addEnumValuesToData(row, data);
        }
    }
    return data;
}

// Event Handlers
async function handleProcessSheet() {
    const sheetData = getSheetData();
    try {
        const response = await fetch('/process_sheet', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ sheetData }),
        });
        const result = await response.json();
        if (result.status === 'success') {
            alert('Sheet processed successfully!');
        } else {
            alert('Error: ' + result.message);
        }
    } catch (error) {
        alert('Error processing sheet: ' + error.message);
    }
}

// Validation Functions
function isCamelCase(str) {
    // Check if string starts with a letter and contains no spaces or special characters
    return /^[a-zA-Z][a-zA-Z0-9]*$/.test(str);
}

async function handleInputValidation(e) {
    const element = e.target;
    if (element.classList.contains('cell-input')) {
        element.classList.remove('validation-error');
        removeTooltip();
        
        // Get the column index to identify field type
        const columnIndex = Array.from(element.closest('td').parentNode.children).indexOf(element.closest('td'));
        
        // Validate form name (4th column)
        if (columnIndex === 3 && element.closest('tr').classList.contains('task-row')) {
            const value = element.value.trim();
            if (value && !isCamelCase(value)) {
                element.classList.add('validation-error');
                showTooltip(element, {
                    isValid: false,
                    error: 'Form name must be in camelCase format',
                    suggestions: [
                        'Start with a lowercase letter',
                        'Use no spaces or special characters',
                        'Use uppercase letters for word boundaries',
                        'Example: myFormName'
                    ]
                });
            }
        }
        
        // Validate predicates
        if (element.classList.contains('predicate-input')) {
            await validateField(element, 'predicate');
        }
        
        // Validate actions
        if (element.classList.contains('action-input')) {
            await validateField(element, 'action');
        }

        // Validate field validation code (column 13)
        if (columnIndex === 13) {
            await validateField(element, 'code');
        }
    }
}

async function validateField(element, fieldType) {
    const result = await validatePythonSyntax(element.value, fieldType);
    if (!result.isValid) {
        element.classList.add('validation-error');
        showTooltip(element, result);
    }
}

async function validatePythonSyntax(code, fieldType = 'code') {
    try {
        const response = await fetch('/validate_syntax', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ code, fieldType }),
        });
        const result = await response.json();
        return result;
    } catch (error) {
        return { 
            isValid: false, 
            error: 'Network error occurred',
            suggestions: ['Check your internet connection']
        };
    }
}

// UI Functions
function showTooltip(element, errorInfo) {
    removeTooltip();
    const tooltip = document.createElement('div');
    tooltip.className = 'tooltip';
    
    tooltip.innerHTML = `<div>${errorInfo.error}</div>`;
    
    if (errorInfo.errorLine) {
        const errorDetails = document.createElement('div');
        errorDetails.className = 'error-details';
        errorDetails.innerHTML = `
            <div class="error-line">${errorInfo.errorLine}</div>
            <div class="error-line">${errorInfo.errorPointer}</div>
        `;
        tooltip.appendChild(errorDetails);
    }
    
    if (errorInfo.suggestions?.length > 0) {
        const suggestions = document.createElement('div');
        suggestions.className = 'error-suggestions';
        suggestions.innerHTML = `
            Suggestions:
            <ul>
                ${errorInfo.suggestions.map(s => `<li>${s}</li>`).join('')}
            </ul>
        `;
        tooltip.appendChild(suggestions);
    }
    
    positionTooltip(tooltip, element);
    document.body.appendChild(tooltip);
    activeTooltip = tooltip;
}

function removeTooltip() {
    if (activeTooltip) {
        activeTooltip.remove();
        activeTooltip = null;
    }
}

function positionTooltip(tooltip, element) {
    const rect = element.getBoundingClientRect();
    tooltip.style.top = `${rect.bottom + window.scrollY + 5}px`;
    tooltip.style.left = `${rect.left + window.scrollX}px`;
}

function addDeleteButton(row, type) {
    const deleteButton = document.createElement('div');
    deleteButton.className = 'row-actions';
    deleteButton.innerHTML = `
        <button class="btn-delete" title="Delete row">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path d="M6 6l12 12M6 18L18 6"/>
            </svg>
        </button>
    `;
    row.appendChild(deleteButton);

    // Add delete functionality
    const deleteBtn = row.querySelector('.btn-delete');
    deleteBtn.addEventListener('click', () => {
        if (type === 'task') {
            // If deleting a task, also delete its fields
            let nextRow = row.nextElementSibling;
            while (nextRow && nextRow.classList.contains('field-row')) {
                const nextNextRow = nextRow.nextElementSibling;
                nextRow.remove();
                nextRow = nextNextRow;
            }
            // If this was the current task, disable the Add Field button
            if (row === currentTaskRow) {
                currentTaskRow = null;
                addFieldBtn.disabled = true;
            }
        }
        row.remove();
        renumberRows();
    });
}

function enableEnumRow(enumRow) {
    const enumInput = enumRow.querySelector('.enum-value');
    const addButton = enumRow.querySelector('.btn-add-enum');
    enumInput.disabled = false;
    addButton.disabled = false;
    enumInput.value = ''; // Clear any previous value
    enumRow.style.display = ''; // Show the row
}

function disableEnumRows(row, enumRow) {
    const enumRows = getEnumRows(row);
    enumRows.forEach(row => {
        const enumInput = row.querySelector('.enum-value');
        const addButton = row.querySelector('.btn-add-enum');
        enumInput.disabled = true;
        addButton.disabled = true;
        enumInput.value = '';
        if (row !== enumRow) {
            row.remove();
        } else {
            row.style.display = 'none';
        }
    });
}

function insertEnumRow(enumRow, fieldRow) {
    const lastEnumRow = getLastEnumRow(fieldRow);
    if (lastEnumRow) {
        lastEnumRow.insertAdjacentElement('afterend', enumRow);
    } else {
        fieldRow.insertAdjacentElement('afterend', enumRow);
    }
}

function setupEnumRowHandlers(enumRow, fieldRow) {
    // Add button click handler
    const addButton = enumRow.querySelector('.btn-add-enum');
    addButton.addEventListener('click', () => {
        const newEnumRow = addEnumValueRow(fieldRow, true);
        newEnumRow.style.display = ''; // Make sure new rows are visible
    });

    // Add delete button with same style as row delete button
    const deleteButton = document.createElement('div');
    deleteButton.className = 'row-actions';
    deleteButton.style.position = 'relative';
    deleteButton.style.right = '0';
    deleteButton.innerHTML = `
        <button class="btn-delete" title="Delete enum value">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path d="M6 6l12 12M6 18L18 6"/>
            </svg>
        </button>
    `;

    // Add delete functionality
    const deleteBtn = deleteButton.querySelector('.btn-delete');
    deleteBtn.addEventListener('click', () => {
        // Only remove if there's more than one visible enum value row
        const enumRows = getEnumRows(fieldRow);
        const visibleEnumRows = enumRows.filter(row => row.style.display !== 'none');
        if (visibleEnumRows.length > 1) {
            enumRow.remove();
        }
    });

    enumRow.appendChild(deleteButton);
}

function addEnumValuesToData(row, data) {
    let nextRow = row.nextElementSibling;
    while (nextRow && nextRow.classList.contains('enum-field')) {
        const enumValue = nextRow.querySelector('.enum-value').value.trim();
        if (enumValue) {
            const emptyArray = new Array(7).fill('');
            emptyArray[6] = enumValue; // Variable Enums column
            data.push(emptyArray);
        }
        nextRow = nextRow.nextElementSibling;
    }
}

// Modal Editor Functions
function createCodeEditorModal() {
    const modal = document.createElement('div');
    modal.id = 'codeEditorModal';
    modal.className = 'modal';
    modal.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <h2>Code Editor</h2>
                <span class="close">&times;</span>
            </div>
            <div class="modal-body">
                <div id="modalCodeEditor"></div>
                <div id="lintingErrors" class="linting-errors"></div>
            </div>
            <div class="modal-footer">
                <button id="applyCodeChanges" class="btn-primary">Apply Changes</button>
                <button id="cancelCodeChanges" class="btn-secondary">Cancel</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    
    // Initialize CodeMirror
    const editor = CodeMirror(document.getElementById('modalCodeEditor'), {
        mode: 'python',
        theme: 'default',
        lineNumbers: true,
        indentUnit: 4,
        smartIndent: true,
        indentWithTabs: false,
        lineWrapping: true,
        matchBrackets: true,
        autoCloseBrackets: true,
        styleActiveLine: true,
        extraKeys: {
            'Tab': (cm) => cm.execCommand('indentMore'),
            'Shift-Tab': (cm) => cm.execCommand('indentLess'),
            'Ctrl-/': 'toggleComment',
            'Cmd-/': 'toggleComment',
            'Enter': (cm) => {
                // Smart indentation on Enter
                const cursor = cm.getCursor();
                const line = cm.getLine(cursor.line);
                const indentation = line.match(/^\s*/)[0];
                
                // Check if the line ends with a colon
                if (line.trim().endsWith(':')) {
                    cm.replaceSelection('\n' + indentation + '    ');
                } else {
                    cm.replaceSelection('\n' + indentation);
                }
                return true;
            }
        }
    });
    
    // Get modal elements
    const closeBtn = modal.querySelector('.close');
    const applyBtn = modal.querySelector('#applyCodeChanges');
    const cancelBtn = modal.querySelector('#cancelCodeChanges');
    
    let currentCell = null;
    
    // Close modal handlers
    function closeModal() {
        modal.style.display = 'none';
        currentCell = null;
    }
    
    closeBtn.onclick = closeModal;
    cancelBtn.onclick = closeModal;
    
    window.onclick = (event) => {
        if (event.target === modal) {
            closeModal();
        }
    };
    
    // Apply changes handler
    applyBtn.onclick = async () => {
        if (currentCell) {
            const code = editor.getValue();
            const columnIndex = Array.from(currentCell.closest('td').parentNode.children).indexOf(currentCell.closest('td'));
            const fieldType = currentCell.classList.contains('predicate-input') ? 'predicate' :
                            currentCell.classList.contains('action-input') ? 'action' : 'code';
            
            const result = await validatePythonSyntax(code, fieldType);
            if (result.isValid) {
                // Update the input field value, preserving newlines
                currentCell.value = code;
                currentCell.setAttribute('data-original-code', code);
                
                // Force textarea to preserve whitespace
                currentCell.style.whiteSpace = 'pre';
                currentCell.style.overflowWrap = 'normal';
                currentCell.style.wordBreak = 'keep-all';
                
                // Adjust height to fit content
                currentCell.style.height = 'auto';
                const lines = code.split('\n').length;
                const lineHeight = parseInt(window.getComputedStyle(currentCell).lineHeight);
                const paddingTop = parseInt(window.getComputedStyle(currentCell).paddingTop);
                const paddingBottom = parseInt(window.getComputedStyle(currentCell).paddingBottom);
                const minHeight = Math.max(42, (lines * lineHeight) + paddingTop + paddingBottom);
                currentCell.style.height = minHeight + 'px';
                
                // Trigger input event after setting value
                currentCell.dispatchEvent(new Event('input', { bubbles: true }));
                closeModal();
            } else {
                showLintingErrors(result);
            }
        }
    };
    
    // Editor change handler for live validation
    let lintingTimeout;
    editor.on('change', () => {
        clearTimeout(lintingTimeout);
        lintingTimeout = setTimeout(async () => {
            if (currentCell) {
                const code = editor.getValue();
                const columnIndex = Array.from(currentCell.closest('td').parentNode.children).indexOf(currentCell.closest('td'));
                const fieldType = currentCell.classList.contains('predicate-input') ? 'predicate' :
                                currentCell.classList.contains('action-input') ? 'action' : 'code';
                
                const result = await validatePythonSyntax(code, fieldType);
                showLintingErrors(result);
            }
        }, 500); // Debounce validation for 500ms
    });
    
    return {
        show: (cell) => {
            currentCell = cell;
            // Get the original code if it exists, otherwise use the current value
            const code = cell.getAttribute('data-original-code') || cell.value;
            editor.setValue(code);
            modal.style.display = 'block';
            editor.focus();
            editor.refresh(); // Ensure CodeMirror renders correctly
            // Initial validation
            setTimeout(async () => {
                const columnIndex = Array.from(cell.closest('td').parentNode.children).indexOf(cell.closest('td'));
                const fieldType = cell.classList.contains('predicate-input') ? 'predicate' :
                                cell.classList.contains('action-input') ? 'action' : 'code';
                const result = await validatePythonSyntax(editor.getValue(), fieldType);
                showLintingErrors(result);
            }, 100);
        }
    };
}

function showLintingErrors(result) {
    const lintingErrors = document.getElementById('lintingErrors');
    lintingErrors.innerHTML = '';
    
    if (!result.isValid) {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'error-message';
        errorDiv.textContent = result.error;
        
        if (result.errorLine) {
            const codePreview = document.createElement('pre');
            codePreview.className = 'code-preview';
            codePreview.innerHTML = `${result.errorLine}\n${result.errorPointer}`;
            errorDiv.appendChild(codePreview);
        }
        
        if (result.suggestions?.length > 0) {
            const suggestions = document.createElement('ul');
            suggestions.className = 'suggestions-list';
            result.suggestions.forEach(suggestion => {
                const li = document.createElement('li');
                li.textContent = suggestion;
                suggestions.appendChild(li);
            });
            errorDiv.appendChild(suggestions);
        }
        
        lintingErrors.appendChild(errorDiv);
    }
}

// Context Menu Functions
let activeContextMenu = null;

function createContextMenu(x, y, row) {
    removeContextMenu();
    
    const menu = document.createElement('div');
    menu.className = 'context-menu';
    menu.style.left = `${x}px`;
    menu.style.top = `${y}px`;
    
    menu.innerHTML = `
        <div class="context-menu-item" data-action="add-task-above">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 5v14M5 12h14"/>
            </svg>
            Add Task Above
        </div>
        <div class="context-menu-item" data-action="add-field-above">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 5v14M5 12h14"/>
            </svg>
            Add Field Above
        </div>
        <div class="context-menu-divider"></div>
        <div class="context-menu-item" data-action="add-task-below">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 5v14M5 12h14"/>
            </svg>
            Add Task Below
        </div>
        <div class="context-menu-item" data-action="add-field-below">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 5v14M5 12h14"/>
            </svg>
            Add Field Below
        </div>
    `;
    
    // Add event listeners for menu items
    menu.querySelectorAll('.context-menu-item').forEach(item => {
        item.addEventListener('click', (e) => {
            const action = e.currentTarget.getAttribute('data-action');
            handleContextMenuAction(action, row);
            removeContextMenu();
        });
    });
    
    document.body.appendChild(menu);
    activeContextMenu = menu;
    
    // Adjust menu position if it goes off screen
    const menuRect = menu.getBoundingClientRect();
    const windowWidth = window.innerWidth;
    const windowHeight = window.innerHeight;
    
    if (menuRect.right > windowWidth) {
        menu.style.left = `${windowWidth - menuRect.width - 10}px`;
    }
    if (menuRect.bottom > windowHeight) {
        menu.style.top = `${windowHeight - menuRect.height - 10}px`;
    }
}

function handleContextMenuAction(action, row) {
    const [, type, position] = action.split('-');
    addNewRow(type, row, position);
}

function insertNewRow(type, referenceRow, position) {
    return addNewRow(type, referenceRow, position);
}

function removeContextMenu() {
    if (activeContextMenu) {
        activeContextMenu.remove();
        activeContextMenu = null;
    }
} 