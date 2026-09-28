/* =============================================================================
   RETEC MOTION — cards
   -----------------------------------------------------------------------------
   Tactile depth for the existing cards. Nothing is redesigned: the same card
   simply gains a little weight, a hint of tilt and a moving image.

   Guardrails:
     · ≤ api.reach.tilt (3.2deg) rotation, ≤ api.reach.lift (6px) translation
     · fine pointer only — coarse pointers keep the flat, design-only hover
     · purely event-driven: no idle loop, no tween runs while untouched
   ========================================================================== */
(function (window, document) {
    'use strict';

    /* core.js always runs first (defer order) and publishes the api, so
       this is one shared live reference for the whole module. */
    var motion = window.RETEC_MOTION;

    var SELECTOR = '.work__card, .blog__card, .testimonial-card, .service__item, .process__item';

    function init() {
        if (!motion || !motion.live() || !motion.gsap) return;

        var cards = Array.prototype.slice.call(document.querySelectorAll(SELECTOR));
        if (!cards.length) return;

        /* Touch and reduced-motion visitors get the design's own hover only. */
        if (!motion.fine()) return;

        var gsap = motion.gsap;
        var cleanups = [];

        cards.forEach(function (card) {
            var media = card.querySelector('[data-motion="image"] img, .work__image-img, img');
            /* motion.css neutralises the design's CSS hover lift, so the card's
               resting transform really is zero. Reading it from GSAP instead
               would capture a card mid-entrance and leave it permanently off. */
            var restingY = 0;
            /* images.js publishes the scale it settled on so mouse-out restores
               the right value instead of assuming 1. */
            var restingScale = media
                ? parseFloat(media.getAttribute('data-resting-scale')) || 1
                : 1;
            var hoverScale = restingScale * 1.05;

            var setRotateX = gsap.quickTo(card, 'rotationX', { duration: 0.5, ease: 'power3.out' });
            var setRotateY = gsap.quickTo(card, 'rotationY', { duration: 0.5, ease: 'power3.out' });
            var setY = gsap.quickTo(card, 'y', { duration: 0.5, ease: 'power3.out' });
            /* Scale is NOT a quickTo: GSAP 3.15.0's resetTo warns "scale not
               eligible for reset" on EVERY call for that prop specifically, and
               the warning doubles every time a new quickTo tween is created for
               it. Scale is only changed on enter/leave (never per pointermove),
               so a plain overwriting tween gives the same smooth re-anchor. */
            function mediaScale(value) {
                if (!media) return;
                gsap.killTweensOf(media, 'scale');
                gsap.to(media, { scale: value, duration: 0.6, ease: 'power3.out', overwrite: true });
            }

            function onMove(event) {
                if (event.pointerType && event.pointerType !== 'mouse') return;
                var rect = card.getBoundingClientRect();
                if (!rect.width || !rect.height) return;
                var px = (event.clientX - rect.left) / rect.width - 0.5;
                var py = (event.clientY - rect.top) / rect.height - 0.5;
                setRotateY(px * motion.reach.tilt * 2);
                setRotateX(-py * motion.reach.tilt * 1.4);
            }

            function onEnter() {
                /* The entrance (reveal.js / projects.js) owns y until it lands;
                   hand over explicitly so two engines never write one property. */
                setY(restingY - motion.reach.lift);
                if (mediaScale) mediaScale(hoverScale);
            }

            function onLeave() {
                setRotateX(0);
                setRotateY(0);
                setY(restingY);
                if (mediaScale) mediaScale(restingScale);
            }

            card.addEventListener('pointerenter', onEnter);
            card.addEventListener('pointermove', onMove);
            card.addEventListener('pointerleave', onLeave);
            card.addEventListener('pointercancel', onLeave);

            cleanups.push(function () {
                card.removeEventListener('pointerenter', onEnter);
                card.removeEventListener('pointermove', onMove);
                card.removeEventListener('pointerleave', onLeave);
                card.removeEventListener('pointercancel', onLeave);
                gsap.killTweensOf(card);
                if (media) gsap.killTweensOf(media);
                motion.resetTransform(card);
            });
        });

        if (cleanups.length) motion.onCleanup(function () {
            cleanups.forEach(function (fn) { fn(); });
        });
    }

    motion.onReady(init);
})(window, document);
