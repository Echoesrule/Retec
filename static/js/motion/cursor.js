/* =============================================================================
   RETEC MOTION — cursor
   -----------------------------------------------------------------------------
   A small dot that grows into a labelled disc on meaningful targets. Desktop
   fine pointers only; it never appears on touch or under reduced motion, and
   the native cursor is left completely untouched everywhere else.

   States are declared with data attributes:
     data-cursor="view"   → VIEW   (project imagery)
     data-cursor="arrow"  → ↗      (primary actions)
     data-cursor="drag"   → DRAG   (testimonial carousel)
     data-cursor="text"   → caret affordance for inputs
   ========================================================================== */
(function (window, document) {
    'use strict';

    /* core.js always runs first (defer order) and publishes the api, so
       this is one shared live reference for the whole module. */
    var motion = window.RETEC_MOTION;

    var LABELS = { view: 'VIEW', arrow: '↗', drag: 'DRAG', text: 'I-beam' };

    function init() {
        if (!motion || !motion.live() || !motion.gsap) return;

        if (!motion.fine()) return;
        if (window.matchMedia('(hover: none)').matches) return;

        var gsap = motion.gsap;
        var doc = document.documentElement;

        var cursor = document.createElement('div');
        cursor.className = 'retec-cursor';
        cursor.setAttribute('aria-hidden', 'true');
        cursor.innerHTML = '<span class="retec-cursor__dot"></span><span class="retec-cursor__label"></span>';
        document.body.appendChild(cursor);

        var label = cursor.querySelector('.retec-cursor__label');

        var setX = gsap.quickTo(cursor, 'x', { duration: 0.22, ease: 'power3.out' });
        var setY = gsap.quickTo(cursor, 'y', { duration: 0.22, ease: 'power3.out' });

        var visible = false;
        var current = null;

        function show() {
            if (visible) return;
            visible = true;
            cursor.classList.add('is-active');
        }

        function hide() {
            if (!visible) return;
            visible = false;
            current = null;
            cursor.classList.remove('is-active', 'is-labelled', 'is-caret');
        }

        function onMove(event) {
            setX(event.clientX);
            setY(event.clientY);
            show();
        }

        function onOver(event) {
            var target = event.target.closest ? event.target.closest('[data-cursor]') : null;
            if (target === current) return;
            current = target;
            if (!target) {
                cursor.classList.remove('is-labelled', 'is-caret');
                return;
            }
            var kind = target.getAttribute('data-cursor');
            /* A text field wants a caret, not a 46px disc. */
            cursor.classList.toggle('is-caret', kind === 'text');
            label.textContent = LABELS[kind] || '';
            cursor.classList.add('is-labelled');
        }

        function onDown() { cursor.classList.add('is-pressed'); }
        function onUp() { cursor.classList.remove('is-pressed'); }

        function onLeaveWindow() { hide(); }
        function onEnterWindow(event) {
            /* Only fade in for real pointing devices. */
            if (event.pointerType && event.pointerType !== 'mouse') return;
            show();
        }

        document.addEventListener('pointermove', onMove, { passive: true });
        document.addEventListener('pointerover', onOver, { passive: true });
        document.addEventListener('pointerdown', onDown, { passive: true });
        document.addEventListener('pointerup', onUp, { passive: true });
        document.documentElement.addEventListener('mouseleave', onLeaveWindow);
        document.documentElement.addEventListener('mouseenter', onEnterWindow);

        /* Touch on a hybrid device must not strand the cursor on screen. */
        document.addEventListener('touchstart', hide, { passive: true });

        motion.onCleanup(function () {
            document.removeEventListener('pointermove', onMove);
            document.removeEventListener('pointerover', onOver);
            document.removeEventListener('pointerdown', onDown);
            document.removeEventListener('pointerup', onUp);
            document.removeEventListener('touchstart', hide);
            document.documentElement.removeEventListener('mouseleave', onLeaveWindow);
            document.documentElement.removeEventListener('mouseenter', onEnterWindow);
            gsap.killTweensOf(cursor);
            if (cursor.parentNode) cursor.parentNode.removeChild(cursor);
            doc.classList.remove('retec-cursor-active');
        });
    }

    motion.onReady(init);
})(window, document);
