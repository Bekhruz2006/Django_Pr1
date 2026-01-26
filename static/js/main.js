
document.addEventListener('DOMContentLoaded', function() {
    console.log('App initialized');
    initTooltips();
    initConfirmDialogs();
});

function initTooltips() {
    const tooltips = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    tooltips.forEach(el => new bootstrap.Tooltip(el));
}

function initConfirmDialogs() {
    document.querySelectorAll('[data-confirm]').forEach(element => {
        element.addEventListener('click', function(e) {
            if (!confirm(this.dataset.confirm)) {
                e.preventDefault();
            }
        });
    });
}

function sortTable(header) {
    const table = header.closest('table');
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    const columnIndex = Array.from(header.parentElement.children).indexOf(header);
    const isAscending = header.classList.contains('asc');
    
    table.querySelectorAll('th').forEach(th => {
        th.classList.remove('asc', 'desc');
    });
    
    header.classList.add(isAscending ? 'desc' : 'asc');
    
    rows.sort((a, b) => {
        const aValue = a.cells[columnIndex].textContent.trim();
        const bValue = b.cells[columnIndex].textContent.trim();
        
        const aNum = parseFloat(aValue.replace(/[^0-9.-]/g, ''));
        const bNum = parseFloat(bValue.replace(/[^0-9.-]/g, ''));
        
        if (!isNaN(aNum) && !isNaN(bNum)) {
            return isAscending ? bNum - aNum : aNum - bNum;
        }
        
        return isAscending ? bValue.localeCompare(aValue) : aValue.localeCompare(bValue);
    });
    
    rows.forEach(row => tbody.appendChild(row));
}