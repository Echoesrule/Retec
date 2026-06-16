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
            document.body.style.overflow = navMenu.classList.contains('nav__menu--open') ? 'hidden' : '';
        });
    }

    navLinks.forEach(link => {
        link.addEventListener('click', () => {
            navToggle.classList.remove('nav__toggle--active');
            navMenu.classList.remove('nav__menu--open');
            document.body.style.overflow = '';
        });
    });

    /* ===== SMOOTH SCROLL ===== */
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                e.preventDefault();
                target.scrollIntoView({ behavior: 'smooth' });
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
                e.preventDefault();
                pageContent.classList.add('page-content--fading');
                setTimeout(() => {
                    window.location.href = href;
                }, 220);
            });
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
