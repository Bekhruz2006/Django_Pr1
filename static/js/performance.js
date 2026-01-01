/**
 * Модуль оптимизации производительности
 * Включает: ленивую загрузку, дебаунсинг, кеширование
 */

// ============================================
// 1. ЛЕНИВАЯ ЗАГРУЗКА ИЗОБРАЖЕНИЙ
// ============================================
class LazyLoader {
    constructor() {
        this.images = document.querySelectorAll('img[data-src]');
        this.init();
    }
    
    init() {
        if ('IntersectionObserver' in window) {
            const imageObserver = new IntersectionObserver((entries, observer) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        const img = entry.target;
                        img.src = img.dataset.src;
                        img.removeAttribute('data-src');
                        imageObserver.unobserve(img);
                    }
                });
            });
            
            this.images.forEach(img => imageObserver.observe(img));
        } else {
            // Fallback для старых браузеров
            this.images.forEach(img => {
                img.src = img.dataset.src;
            });
        }
    }
}

// ============================================
// 2. ДЕБАУНСИНГ И ТРОТТЛИНГ
// ============================================
const debounce = (func, wait = 300) => {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
};

const throttle = (func, limit = 100) => {
    let inThrottle;
    return function(...args) {
        if (!inThrottle) {
            func.apply(this, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
};

// ============================================
// 3. КЕШИРОВАНИЕ AJAX-ЗАПРОСОВ
// ============================================
class CacheManager {
    constructor(ttl = 5 * 60 * 1000) { // 5 минут по умолчанию
        this.cache = new Map();
        this.ttl = ttl;
    }
    
    set(key, value) {
        const item = {
            value: value,
            expiry: Date.now() + this.ttl
        };
        this.cache.set(key, item);
    }
    
    get(key) {
        const item = this.cache.get(key);
        if (!item) return null;
        
        if (Date.now() > item.expiry) {
            this.cache.delete(key);
            return null;
        }
        
        return item.value;
    }
    
    clear() {
        this.cache.clear();
    }
}

const cache = new CacheManager();

// Обертка для fetch с кешированием
async function cachedFetch(url, options = {}) {
    const cacheKey = url + JSON.stringify(options);
    
    // Проверяем кеш
    const cached = cache.get(cacheKey);
    if (cached && !options.ignoreCache) {
        return Promise.resolve(cached);
    }
    
    // Делаем запрос
    try {
        const response = await fetch(url, options);
        const data = await response.json();
        
        // Сохраняем в кеш только успешные GET-запросы
        if (response.ok && (!options.method || options.method === 'GET')) {
            cache.set(cacheKey, data);
        }
        
        return data;
    } catch (error) {
        console.error('Fetch error:', error);
        throw error;
    }
}

// ============================================
// 4. ОПТИМИЗАЦИЯ СКРОЛЛА
// ============================================
const optimizeScroll = () => {
    let ticking = false;
    
    const handleScroll = () => {
        if (!ticking) {
            window.requestAnimationFrame(() => {
                // Ваши действия при скролле
                document.body.classList.toggle('scrolled', window.pageYOffset > 50);
                ticking = false;
            });
            ticking = true;
        }
    };
    
    window.addEventListener('scroll', handleScroll, { passive: true });
};

// ============================================
// 5. ПРЕДЗАГРУЗКА ССЫЛОК ПРИ HOVER
// ============================================
class LinkPrefetcher {
    constructor() {
        this.prefetched = new Set();
        this.init();
    }
    
    init() {
        document.addEventListener('mouseover', (e) => {
            const link = e.target.closest('a[href^="/"]');
            if (link && !this.prefetched.has(link.href)) {
                this.prefetch(link.href);
            }
        });
    }
    
    prefetch(url) {
        const link = document.createElement('link');
        link.rel = 'prefetch';
        link.href = url;
        document.head.appendChild(link);
        this.prefetched.add(url);
    }
}

// ============================================
// 6. ОПТИМИЗАЦИЯ ФОРМ
// ============================================
class FormOptimizer {
    constructor() {
        this.forms = document.querySelectorAll('form');
        this.init();
    }
    
    init() {
        this.forms.forEach(form => {
            // Автосохранение в localStorage
            if (form.dataset.autosave) {
                this.enableAutosave(form);
            }
            
            // Предотвращение двойной отправки
            form.addEventListener('submit', (e) => {
                const submitBtn = form.querySelector('button[type="submit"]');
                if (submitBtn && !submitBtn.disabled) {
                    submitBtn.disabled = true;
                    submitBtn.dataset.originalText = submitBtn.innerHTML;
                    submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Отправка...';
                    
                    // Включаем кнопку обратно через 3 секунды (на случай ошибки)
                    setTimeout(() => {
                        submitBtn.disabled = false;
                        submitBtn.innerHTML = submitBtn.dataset.originalText;
                    }, 3000);
                }
            });
        });
    }
    
    enableAutosave(form) {
        const formId = form.id || 'form_' + Date.now();
        
        // Восстанавливаем данные при загрузке
        const saved = localStorage.getItem('autosave_' + formId);
        if (saved) {
            try {
                const data = JSON.parse(saved);
                Object.keys(data).forEach(name => {
                    const field = form.elements[name];
                    if (field) field.value = data[name];
                });
            } catch (e) {
                console.error('Autosave restore error:', e);
            }
        }
        
        // Сохраняем при изменении (с дебаунсингом)
        const saveData = debounce(() => {
            const data = {};
            Array.from(form.elements).forEach(el => {
                if (el.name && el.type !== 'password') {
                    data[el.name] = el.value;
                }
            });
            localStorage.setItem('autosave_' + formId, JSON.stringify(data));
        }, 1000);
        
        form.addEventListener('input', saveData);
        
        // Очищаем при успешной отправке
        form.addEventListener('submit', () => {
            localStorage.removeItem('autosave_' + formId);
        });
    }
}

// ============================================
// 7. ОПТИМИЗАЦИЯ ТАБЛИЦ
// ============================================
class TableOptimizer {
    constructor(selector = 'table') {
        this.tables = document.querySelectorAll(selector);
        this.init();
    }
    
    init() {
        this.tables.forEach(table => {
            if (table.rows.length > 50) {
                this.virtualize(table);
            }
        });
    }
    
    virtualize(table) {
        // Виртуализация больших таблиц
        const tbody = table.querySelector('tbody');
        if (!tbody) return;
        
        const rows = Array.from(tbody.rows);
        const rowHeight = 50; // примерная высота строки
        const visibleRows = Math.ceil(window.innerHeight / rowHeight) + 5;
        
        let startIndex = 0;
        
        const render = throttle(() => {
            const scrollTop = table.parentElement.scrollTop || 0;
            startIndex = Math.floor(scrollTop / rowHeight);
            const endIndex = Math.min(startIndex + visibleRows, rows.length);
            
            // Скрываем все строки
            rows.forEach((row, i) => {
                row.style.display = (i >= startIndex && i < endIndex) ? '' : 'none';
            });
        }, 100);
        
        table.parentElement.addEventListener('scroll', render);
        render();
    }
}

// ============================================
// 8. ИНИЦИАЛИЗАЦИЯ
// ============================================
document.addEventListener('DOMContentLoaded', () => {
    console.log('🚀 Performance optimization initialized');
    
    // Запускаем оптимизаторы
    new LazyLoader();
    new LinkPrefetcher();
    new FormOptimizer();
    new TableOptimizer();
    optimizeScroll();
    
    // Очищаем кеш при выходе
    window.addEventListener('beforeunload', () => {
        // Не очищаем полностью, чтобы сохранить между вкладками
        // cache.clear();
    });
    
    // Экспортируем утилиты в глобальную область
    window.PerformanceUtils = {
        debounce,
        throttle,
        cachedFetch,
        cache
    };
});

// ============================================
// 9. МЕТРИКИ ПРОИЗВОДИТЕЛЬНОСТИ
// ============================================
if ('PerformanceObserver' in window) {
    // Отслеживание времени загрузки
    const perfObserver = new PerformanceObserver((list) => {
        list.getEntries().forEach((entry) => {
            console.log('⏱️ Performance:', entry.name, entry.duration.toFixed(2) + 'ms');
        });
    });
    
    perfObserver.observe({ entryTypes: ['measure', 'navigation', 'resource'] });
}

// Измерение времени до первой отрисовки контента
window.addEventListener('load', () => {
    const perfData = performance.getEntriesByType('navigation')[0];
    if (perfData) {
        console.log('📊 Page Load Stats:');
        console.log('  DOM Content Loaded:', perfData.domContentLoadedEventEnd - perfData.domContentLoadedEventStart, 'ms');
        console.log('  Full Load:', perfData.loadEventEnd - perfData.loadEventStart, 'ms');
        console.log('  DOM Interactive:', perfData.domInteractive - perfData.fetchStart, 'ms');
    }
});