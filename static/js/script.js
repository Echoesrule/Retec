document.addEventListener('DOMContentLoaded', () => {

    const header = document.getElementById('header');
    const navToggle = document.getElementById('nav-toggle');
    const navMenu = document.getElementById('nav-menu');
    const navLinks = document.querySelectorAll('.nav__link');
    const pageContent = document.getElementById('pageContent');

    /* ===== HEADER SCROLL ===== */
    window.addEventListener('scroll', () => {
        if (window.pageYOffset > 60) {
            header.classList.add('header--scrolled');
        } else {
            header.classList.remove('header--scrolled');
        }
    });

    /* ===== MOBILE MENU ===== */
    if (navToggle) {
        navToggle.addEventListener('click', () => {
            navToggle.classList.toggle('nav__toggle--active');
            navMenu.classList.toggle('nav__menu--open');
            const isOpen = navMenu.classList.contains('nav__menu--open');
            navToggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
            document.body.style.overflow = isOpen ? 'hidden' : '';
        });
    }

    navLinks.forEach(link => {
        link.addEventListener('click', () => {
            navToggle.classList.remove('nav__toggle--active');
            navMenu.classList.remove('nav__menu--open');
            navToggle.setAttribute('aria-expanded', 'false');
            document.body.style.overflow = '';
        });
    });

    const scrollToSection = (hash) => {
        if (!hash) return false;
        const target = document.querySelector(hash);
        if (!target) return false;
        pageContent?.classList.remove('page-content--fading');
        target.scrollIntoView({ behavior: 'smooth' });
        history.pushState(null, '', hash);
        return true;
    };

    /* ===== SMOOTH SCROLL ===== */
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            if (scrollToSection(this.getAttribute('href'))) {
                e.preventDefault();
            }
        });
    });

    /* ===== FUN FACT DISMISS ===== */
    const factClose = document.getElementById('factClose');
    const floatingFact = document.getElementById('floatingFact');
    if (factClose && floatingFact) {
        factClose.addEventListener('click', () => {
            floatingFact.classList.add('floating-fact--hidden');
        });
    }

    /* ===== PAGE TRANSITIONS ===== */
    if (pageContent) {
        window.addEventListener('pageshow', () => {
            pageContent.classList.remove('page-content--fading');
        });

        document.querySelectorAll('a[href]').forEach(link => {
            const href = link.getAttribute('href');
            if (!href || href.startsWith('#') || href.startsWith('http') || href.startsWith('//') || link.getAttribute('target') === '_blank') return;
            link.addEventListener('click', (e) => {
                const url = new URL(href, window.location.href);
                const isSamePageHash = url.pathname === window.location.pathname && url.hash;
                if (isSamePageHash && scrollToSection(url.hash)) {
                    e.preventDefault();
                    return;
                }

                e.preventDefault();
                pageContent.classList.add('page-content--fading');
                setTimeout(() => {
                    window.location.href = url.href;
                }, 220);
            });
        });
    }

    /* ===== EMAIL VERIFICATION ===== */
    const emailInput = document.getElementById('subscribe-email');
    const statusEl = document.getElementById('subscribe-status');
    const subBtn = document.getElementById('subscribe-btn');

    if (emailInput && statusEl && subBtn) {
        let checkTimeout;
        emailInput.addEventListener('input', () => {
            clearTimeout(checkTimeout);
            const email = emailInput.value.trim();
            if (!email) {
                statusEl.textContent = '';
                statusEl.className = 'subscribe__status';
                subBtn.disabled = true;
                return;
            }
            statusEl.textContent = 'Checking...';
            statusEl.className = 'subscribe__status subscribe__status--checking';
            subBtn.disabled = true;
            checkTimeout = setTimeout(() => {
                fetch('/verify-email', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({email})
                })
                .then(r => r.json())
                .then(data => {
                    if (data.valid) {
                        statusEl.textContent = data.message;
                        statusEl.className = 'subscribe__status subscribe__status--valid';
                        subBtn.disabled = false;
                    } else {
                        statusEl.textContent = data.message;
                        statusEl.className = 'subscribe__status subscribe__status--invalid';
                        subBtn.disabled = true;
                    }
                })
                .catch(() => {
                    statusEl.textContent = 'Could not verify.';
                    statusEl.className = 'subscribe__status subscribe__status--invalid';
                    subBtn.disabled = true;
                });
            }, 600);
        });
    }

    /* ===== CATEGORY FILTERS ===== */
    const filters = document.querySelectorAll('.work__filter');
    const workGrid = document.querySelector('.work__grid');
    if (filters.length && workGrid) {
        const cards = workGrid.querySelectorAll('.work__card');
        filters.forEach(btn => {
            btn.addEventListener('click', () => {
                filters.forEach(f => f.classList.remove('work__filter--active'));
                btn.classList.add('work__filter--active');
                const filter = btn.dataset.filter;
                cards.forEach(card => {
                    if (filter === 'all') {
                        card.style.display = '';
                    } else {
                        const cat = card.dataset.category || '';
                        card.style.display = cat === filter ? '' : 'none';
                    }
                });
            });
        });
    }

});
