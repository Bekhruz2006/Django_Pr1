document.addEventListener('DOMContentLoaded', function() {
    console.log('Enhanced main.js loaded');
    initThemeToggle();
    initAnimations();
    initTooltips();
    initTableSorting();
    animateNumbers();
    createFloatingShapes();
    initSmoothScroll();
    initParallax();
    initCardAnimations();
});

function initThemeToggle() {
    const savedTheme = localStorage.getItem('theme') || 'light';
    if (savedTheme === 'dark') {
        document.body.classList.add('dark-mode');
    }
    
    const toggleBtn = document.createElement('button');
    toggleBtn.className = 'theme-toggle';
    toggleBtn.innerHTML = '<i class="bi bi-moon-fill"></i>';
    toggleBtn.onclick = toggleTheme;
    document.body.appendChild(toggleBtn);
    
    updateThemeIcon();
}

function toggleTheme() {
    document.body.classList.toggle('dark-mode');
    const isDark = document.body.classList.contains('dark-mode');
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
    updateThemeIcon();
    
    createThemeChangeEffect();
    
    console.log('Theme toggled to:', isDark ? 'dark' : 'light');
}

function updateThemeIcon() {
    const btn = document.querySelector('.theme-toggle');
    if (btn) {
        const isDark = document.body.classList.contains('dark-mode');
        btn.innerHTML = isDark ? '<i class="bi bi-sun-fill"></i>' : '<i class="bi bi-moon-fill"></i>';
    }
}

function createThemeChangeEffect() {
    const effect = document.createElement('div');
    effect.style.cssText = `
        position: fixed;
        top: 50%;
        left: 50%;
        width: 0;
        height: 0;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(37, 99, 235, 0.2) 0%, transparent 70%);
        pointer-events: none;
        z-index: 9999;
        transform: translate(-50%, -50%);
        animation: expandRipple 0.8s ease-out;
    `;
    document.body.appendChild(effect);
    
    setTimeout(() => effect.remove(), 800);
    
    const style = document.createElement('style');
    style.textContent = `
        @keyframes expandRipple {
            0% {
                width: 0;
                height: 0;
                opacity: 1;
            }
            100% {
                width: 200vw;
                height: 200vw;
                opacity: 0;
            }
        }
    `;
    document.head.appendChild(style);
}

function initAnimations() {
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };
    
    const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry, index) => {
            if (entry.isIntersecting) {
                setTimeout(() => {
                    entry.target.classList.add('fade-in');
                }, index * 100);
                observer.unobserve(entry.target);
            }
        });
    }, observerOptions);
    
    document.querySelectorAll('.card').forEach(card => {
        observer.observe(card);
    });
    
    document.querySelectorAll('.alert').forEach(alert => {
        alert.classList.add('slide-in');
    });
}

function initTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

function initTableSorting() {
    document.querySelectorAll('table.sortable thead th').forEach(header => {
        header.style.cursor = 'pointer';
        header.addEventListener('click', function() {
            sortTable(this);
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
    
    rows.forEach(row => {
        row.style.animation = 'fadeIn 0.3s ease-out';
        tbody.appendChild(row);
    });
}

function animateNumbers() {
    const stats = document.querySelectorAll('.stat-number');
    stats.forEach(stat => {
        const target = parseInt(stat.textContent);
        if (isNaN(target)) return;
        
        let current = 0;
        const increment = target / 60;
        const timer = setInterval(() => {
            current += increment;
            if (current >= target) {
                stat.textContent = target;
                clearInterval(timer);
            } else {
                stat.textContent = Math.floor(current);
            }
        }, 20);
    });
}

function createFloatingShapes() {
    const bgDiv = document.createElement('div');
    bgDiv.className = 'animated-bg';
    
    for (let i = 1; i <= 3; i++) {
        const shape = document.createElement('div');
        shape.className = `floating-shape shape-${i}`;
        bgDiv.appendChild(shape);
    }
    
    document.body.insertBefore(bgDiv, document.body.firstChild);
}

function initSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            const href = this.getAttribute('href');
            if (href === '#') return;
            
            e.preventDefault();
            const target = document.querySelector(href);
            if (target) {
                target.scrollIntoView({ 
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });
}

function initParallax() {
    let ticking = false;
    
    window.addEventListener('scroll', function() {
        if (!ticking) {
            window.requestAnimationFrame(function() {
                const scrolled = window.pageYOffset;
                const shapes = document.querySelectorAll('.floating-shape');
                
                shapes.forEach((shape, index) => {
                    const speed = 0.3 + (index * 0.15);
                    shape.style.transform = `translateY(${scrolled * speed}px)`;
                });
                
                ticking = false;
            });
            
            ticking = true;
        }
    });
}

function initCardAnimations() {
    document.querySelectorAll('.stat-card').forEach(card => {
        card.addEventListener('click', function() {
            this.style.animation = 'pulse 0.5s ease-out';
            setTimeout(() => {
                this.style.animation = '';
            }, 500);
        });
    });
}

document.querySelectorAll('[data-confirm]').forEach(element => {
    element.addEventListener('click', function(e) {
        if (!confirm(this.dataset.confirm)) {
            e.preventDefault();
        }
    });
});

window.addEventListener('load', function() {
    document.body.classList.add('loaded');
    
    setTimeout(() => {
        document.querySelectorAll('.btn').forEach((btn, index) => {
            setTimeout(() => {
                btn.style.animation = 'fadeIn 0.5s ease-out';
            }, index * 50);
        });
    }, 300);
});

function createRipple(event) {
    const button = event.currentTarget;
    const ripple = document.createElement('span');
    const diameter = Math.max(button.clientWidth, button.clientHeight);
    const radius = diameter / 2;
    
    ripple.style.width = ripple.style.height = `${diameter}px`;
    ripple.style.left = `${event.clientX - button.offsetLeft - radius}px`;
    ripple.style.top = `${event.clientY - button.offsetTop - radius}px`;
    ripple.classList.add('ripple');
    
    const rippleEffect = button.getElementsByClassName('ripple')[0];
    if (rippleEffect) {
        rippleEffect.remove();
    }
    
    button.appendChild(ripple);
}

document.querySelectorAll('.btn').forEach(button => {
    button.addEventListener('click', createRipple);
});

const style = document.createElement('style');
style.textContent = `
    .ripple {
        position: absolute;
        border-radius: 50%;
        background: rgba(255, 255, 255, 0.6);
        transform: scale(0);
        animation: ripple-animation 0.6s ease-out;
        pointer-events: none;
    }
    
    @keyframes ripple-animation {
        to {
            transform: scale(4);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);