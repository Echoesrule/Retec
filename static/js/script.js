document.addEventListener('DOMContentLoaded', () => {

    const navToggle = document.getElementById('nav-toggle');
    const navMenu = document.getElementById('nav-menu');
    const motion = window.RETEC_MOTION || null;

    /* ===== MOBILE MENU =====
       State only. Scrolling, transitions and the reveal of the items themselves
       are owned by the motion system (core.js / navigation.js). */
    const setNavMenu = (open) => {
        if (!navToggle || !navMenu) return;
        navToggle.classList.toggle('nav__toggle--active', open);
        navMenu.classList.toggle('nav__menu--open', open);
        navToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
        if (motion) motion.setScrollLocked(open);
        else document.body.style.overflow = open ? 'hidden' : '';
    };

    if (navToggle) {
        navToggle.addEventListener('click', () => setNavMenu(!navMenu.classList.contains('nav__menu--open')));
    }
    if (navMenu) {
        navMenu.addEventListener('click', (e) => {
            if (e.target.closest('a')) setNavMenu(false);
        });
    }
    /* Escape closes the drawer, as expected of any overlay. */
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && navMenu && navMenu.classList.contains('nav__menu--open')) {
            setNavMenu(false);
            navToggle && navToggle.focus();
        }
    });

    /* ===== FUN FACT DISMISS ===== */
    const factClose = document.getElementById('factClose');
    const floatingFact = document.getElementById('floatingFact');
    if (factClose && floatingFact) {
        factClose.addEventListener('click', () => {
            floatingFact.classList.add('floating-fact--hidden');
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
                    statusEl.textContent = data.message;
                    statusEl.className = 'subscribe__status ' + (data.valid
                        ? 'subscribe__status--valid'
                        : 'subscribe__status--invalid');
                    subBtn.disabled = !data.valid;
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
        const applyFilter = (btn) => {
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
        };
        filters.forEach(btn => btn.addEventListener('click', () => applyFilter(btn)));
    }

    /* ===== TESTIMONIALS CAROUSEL ===== */
    const tTrack = document.querySelector('.testimonials__track');
    if (tTrack) {
        const tPrev = document.querySelector('.testimonials__arrow--prev');
        const tNext = document.querySelector('.testimonials__arrow--next');
        const tCards = Array.from(tTrack.querySelectorAll('.testimonial-card'));

        const tStep = () => {
            const first = tCards[0];
            if (!first) return 0;
            const gap = parseFloat(getComputedStyle(tTrack).columnGap) || 0;
            return first.getBoundingClientRect().width + gap;
        };

        const tUpdate = () => {
            const max = tTrack.scrollWidth - tTrack.clientWidth;
            if (tPrev) tPrev.disabled = tTrack.scrollLeft <= 1;
            if (tNext) tNext.disabled = tTrack.scrollLeft >= max - 1;
        };

        if (tPrev) tPrev.addEventListener('click', () => tTrack.scrollBy({ left: -tStep(), behavior: 'smooth' }));
        if (tNext) tNext.addEventListener('click', () => tTrack.scrollBy({ left: tStep(), behavior: 'smooth' }));
        tTrack.addEventListener('scroll', () => requestAnimationFrame(tUpdate), { passive: true });

        let tDrag = false;
        let tStartX = 0;
        let tStartScroll = 0;

        tTrack.addEventListener('pointerdown', (e) => {
            if (e.pointerType !== 'mouse') return;
            tDrag = true;
            tStartX = e.pageX;
            tStartScroll = tTrack.scrollLeft;
            tTrack.classList.add('testimonials__track--dragging');
            tTrack.setPointerCapture(e.pointerId);
        });

        tTrack.addEventListener('pointermove', (e) => {
            if (!tDrag) return;
            tTrack.scrollLeft = tStartScroll - (e.pageX - tStartX);
        });

        const tEndDrag = (e) => {
            if (!tDrag) return;
            tDrag = false;
            tTrack.classList.remove('testimonials__track--dragging');
            try { tTrack.releasePointerCapture(e.pointerId); } catch (_) {}
        };

        tTrack.addEventListener('pointerup', tEndDrag);
        tTrack.addEventListener('pointercancel', tEndDrag);

        window.addEventListener('resize', tUpdate);
        tUpdate();
    }

});