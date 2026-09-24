/* RETEC landing page — hero entrance + selected-work marquee.
   Powered by Anime.js v4 (window.anime). No-JS safe: initial states only ever
   hide content once a CSS class is added by JavaScript, so pages stay
   fully readable if the animation library is missing or JS is disabled. */
(function () {
    'use strict';

    if (!window.anime) return;

    var hero = document.getElementById('hero');
    if (!hero) return;

    var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var isSmallScreen = window.matchMedia && window.matchMedia('(max-width: 768px)').matches;

    function q(sel) {
        return hero.querySelector(sel);
    }

    function qa(sel) {
        return Array.prototype.slice.call(hero.querySelectorAll(sel));
    }

    /* Gate initial hidden states behind a JS-added class so the hero is
       fully usable without JavaScript or when Anime.js fails to load. */
    function setInitialStates() {
        if (reduceMotion) return;
        hero.classList.add('hero-editorial--anim');
    }

    /* ————— Left column entrance ————— */
    function animateHeroEntrance() {
        if (reduceMotion) return;

        function fadeUp(el, delay, distance) {
            if (!el) return;
            anime.animate(el, {
                opacity: [0, 1],
                translateY: [distance, 0],
                duration: 750,
                delay: delay,
                easing: 'easeOutCubic'
            });
        }

        fadeUp(q('.hero-editorial__pill'), 120, 22);
        fadeUp(q('.hero-editorial__title'), 240, 25);
        fadeUp(q('.hero-editorial__title-lite'), 380, 18);
        fadeUp(q('.hero-editorial__desc'), 520, 22);
        fadeUp(q('.hero-editorial__actions'), 640, 20);
        fadeUp(q('.hero-editorial__social'), 760, 20);
    }

    /* ————— Right-side visual composition ————— */
    function animateHeroVisual() {
        if (reduceMotion) return;

        var visual = q('.hero-editorial__visual');
        if (!visual) return;

        anime.animate(visual, {
            opacity: [0, 1],
            scale: [0.96, 1],
            translateY: [12, 0],
            duration: 1000,
            delay: 400,
            easing: 'easeOutCubic'
        });
    }

    /* ————— Animated SVG paths (only when a [data-anim="dash"] element is present) ————— */
    function animateSvgPaths() {
        if (reduceMotion) return;

        qa('[data-anim="dash"]').forEach(function (path) {
            if (!path.getTotalLength) return;
            var length = path.getTotalLength();
            if (!length) return;
            path.style.strokeDasharray = length;
            path.style.strokeDashoffset = length;
            anime.animate(path, {
                strokeDashoffset: [length, 0],
                duration: 2400,
                delay: 900,
                easing: 'easeOutCubic'
            });
            anime.animate(path, {
                strokeDashoffset: [0, -length],
                duration: 22000,
                easing: 'linear',
                loop: true
            });
        });
    }

    /* ————— Featured project card: entrance then continuous float ————— */
    function animateProjectCard() {
        var card = q('.hero-editorial__card');
        if (!card) return;

        if (reduceMotion) return;

        anime.animate(card, {
            opacity: [0, 1],
            translateY: [15, 0],
            duration: 700,
            delay: 1050,
            easing: 'easeOutCubic'
        });

        window.setTimeout(function () {
            card._float = anime.animate(card, {
                translateY: [0, isSmallScreen ? -4 : -6, 0],
                duration: 7500,
                easing: 'easeInOutSine',
                loop: true
            });
        }, 2000);
    }

    /* ————— Hover interactions ————— */
    function setupHeroInteractions() {
        var card = q('.hero-editorial__card');
        if (!card) return;

        card.addEventListener('pointerenter', function () {
            if (reduceMotion) return;
            if (card._float) card._float.pause();
            card.classList.add('hero-editorial__card--hover');
        });
        card.addEventListener('pointerleave', function () {
            if (reduceMotion) return;
            card.classList.remove('hero-editorial__card--hover');
            if (card._float) card._float.play();
        });
    }

    /* ————— Selected-work marquee ————— */
    /* Driven by a CSS animation (keyframes translate the list by -50% of its
       own width), which keeps the seam pixel-aligned at all times regardless
       of font/layout reflows. Hover pause is handled in CSS too. */

    function init() {
        setInitialStates();
        animateHeroEntrance();
        animateHeroVisual();
        animateSvgPaths();
        animateProjectCard();
        setupHeroInteractions();
    }

    init();
})();