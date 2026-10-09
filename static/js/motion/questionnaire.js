/* =============================================================================
   RETEC MOTION — questionnaire
   -----------------------------------------------------------------------------
   Turns the discovery questionnaire into a sequential wizard: one section at a
   time, a progress bar, Back/Next, and per-step validation. It is a progressive
   enhancement — with JS off every section stays visible and the plain submit
   button works, so the server is always the final authority.

   Markup contract:  <form data-qs-wizard data-qs-start="<first-error-key>">
                       [data-qs-step]  [data-qs-title]  [data-qs-jump]
                       [data-qs-prev]  [data-qs-next]   [data-qs-submit]

   Motion honours the shared runtime: step transitions only animate when the
   motion system is live, otherwise they swap instantly but still work.
   ========================================================================== */
(function (window, document) {
    'use strict';

    var motion = window.RETEC_MOTION;
    if (!motion) return;

    function init() {
        var form = document.querySelector('[data-qs-wizard]');
        if (!form) return;

        var steps = Array.prototype.slice.call(form.querySelectorAll('[data-qs-step]'));
        if (steps.length < 2) return;

        var prevBtn = form.querySelector('[data-qs-prev]');
        var nextBtn = form.querySelector('[data-qs-next]');
        var submitBtn = form.querySelector('[data-qs-submit]');
        var fill = form.querySelector('.qs-progress__fill');
        var countEl = form.querySelector('[data-qs-current]');
        var titleEl = form.querySelector('[data-qs-title]');
        var dots = Array.prototype.slice.call(form.querySelectorAll('[data-qs-jump]'));

        var total = steps.length;
        var current = 0;
        var animating = false;
        var gsap = motion.gsap;

        form.classList.add('qs-wizard--js');

        function canAnimate() {
            return !!(gsap && motion.live && motion.live());
        }

        function clamp(index) {
            return Math.max(0, Math.min(total - 1, index));
        }

        /* A step counts as "answered" once the visitor has moved past it. The
           progress bar is driven by this, so it fills as stages are completed. */
        var answered = steps.map(function () { return false; });

        var startKey = form.getAttribute('data-qs-start') || '';
        if (startKey) {
            steps.some(function (step, index) {
                if (step.id === 'qs-' + startKey) { current = index; return true; }
                return false;
            });
        }
        for (var a = 0; a < current; a += 1) answered[a] = true;

        /* --------------------------------------------------------------- paint */
        function answeredCount() {
            var n = 0;
            answered.forEach(function (done) { if (done) n += 1; });
            return n;
        }

        function paintProgress() {
            if (fill) fill.style.width = ((answeredCount() / total) * 100) + '%';
            if (countEl) countEl.textContent = String(current + 1);
            if (titleEl) titleEl.textContent = steps[current].getAttribute('data-qs-title') || '';
            if (prevBtn) prevBtn.disabled = current === 0;
            form.classList.toggle('qs-wizard--last', current === total - 1);

            dots.forEach(function (dot, index) {
                dot.classList.toggle('is-active', index === current);
                dot.classList.toggle('is-done', answered[index] && index !== current);
                dot.setAttribute('aria-current', index === current ? 'step' : 'false');
            });
        }

        function activate(index) {
            steps.forEach(function (step, i) {
                var on = i === index;
                step.classList.toggle('is-active', on);
                /* Belt and braces: the hidden attribute guarantees one-step-at-a-
                   time behaviour even if an older stylesheet is still cached. */
                step.hidden = !on;
                step.setAttribute('aria-hidden', on ? 'false' : 'true');
            });
        }

        /* ------------------------------------------------------------ focus/a11y */
        function focusStep() {
            var step = steps[current];
            var target = step.querySelector(
                'input:not([type="hidden"]), select, textarea, button');
            if (target && target.offsetParent !== null) {
                try { target.focus({ preventScroll: true }); }
                catch (_) { target.focus(); }
            }
            if (motion.scrollTo) {
                motion.scrollTo(step, { offset: 140, duration: 0.6 });
            }
        }

        function shake(step) {
            if (motion.reduced && motion.reduced()) return;
            step.classList.remove('is-shake');
            /* reflow so the class re-triggers the keyframes */
            void step.offsetWidth;
            step.classList.add('is-shake');
            window.setTimeout(function () { step.classList.remove('is-shake'); }, 500);
        }

        /* ------------------------------------------------------------ validation */
        function clearFieldError(field) {
            field.classList.remove('qs-field--invalid');
            var note = field.querySelector('.qs-field__error');
            if (note) note.textContent = '';
        }

        function setFieldError(field, message) {
            field.classList.add('qs-field--invalid');
            var note = field.querySelector('.qs-field__error');
            if (!note) {
                note = document.createElement('span');
                note.className = 'qs-field__error';
                field.appendChild(note);
            }
            note.textContent = message || 'Please check this field.';
        }

        function validateStep(step) {
            var fields = Array.prototype.slice.call(step.querySelectorAll('.qs-field'));
            var firstBad = null;
            fields.forEach(function (field) {
                var bad = null;
                Array.prototype.forEach.call(
                    field.querySelectorAll('input, select, textarea'),
                    function (el) {
                        if (el.type === 'hidden' || bad) return;
                        if (!el.checkValidity()) bad = el;
                    }
                );
                if (bad) {
                    setFieldError(field, bad.validationMessage);
                    if (!firstBad) firstBad = bad;
                } else {
                    clearFieldError(field);
                }
            });
            return firstBad;
        }

        /* Returns the index of the first invalid step, or -1 when all pass. */
        function firstInvalidStep() {
            var bad = -1;
            steps.forEach(function (step, index) {
                if (validateStep(step) && bad === -1) bad = index;
            });
            return bad;
        }

        /* --------------------------------------------------------------- motion */
        function goTo(index, focus) {
            index = clamp(index);
            if (animating) return;

            var target = steps[index];
            if (index === current && target.classList.contains('is-active')) {
                paintProgress();
                if (focus) focusStep();
                return;
            }

            var dir = index > current ? 1 : -1;
            /* Moving forward counts the stages behind us as answered. */
            for (var a = 0; a < index; a += 1) answered[a] = true;

            if (!canAnimate()) {
                current = index;
                activate(current);
                paintProgress();
                if (focus) focusStep();
                return;
            }

            animating = true;
            var from = steps[current];
            gsap.killTweensOf(steps);

            gsap.to(from, {
                opacity: 0,
                y: dir * -14,
                duration: motion.duration.fast,
                ease: motion.ease.standard,
                onComplete: function () {
                    from.classList.remove('is-active');
                    from.hidden = true;
                    gsap.set(from, { clearProps: 'opacity,transform' });

                    current = index;
                    target.hidden = false;
                    target.classList.add('is-active');
                    paintProgress();

                    gsap.fromTo(target,
                        { opacity: 0, y: dir * 18 },
                        {
                            opacity: 1,
                            y: 0,
                            duration: motion.duration.medium,
                            ease: motion.ease.smooth,
                            onComplete: function () {
                                gsap.set(target, { clearProps: 'opacity,transform' });
                                animating = false;
                                if (focus) focusStep();
                            }
                        }
                    );
                }
            });
        }

        /* --------------------------------------------------------------- events */
        if (nextBtn) {
            nextBtn.addEventListener('click', function () {
                if (validateStep(steps[current])) {
                    shake(steps[current]);
                    return;
                }
                if (current < total - 1) goTo(current + 1, true);
            });
        }

        if (prevBtn) {
            prevBtn.addEventListener('click', function () {
                if (current > 0) goTo(current - 1, true);
            });
        }

        dots.forEach(function (dot) {
            dot.addEventListener('click', function () {
                var index = parseInt(dot.getAttribute('data-qs-jump'), 10);
                if (!isNaN(index)) goTo(index, true);
            });
        });

        form.addEventListener('input', function (event) {
            var field = event.target.closest ? event.target.closest('.qs-field') : null;
            if (!field) return;
            var ok = true;
            Array.prototype.forEach.call(
                field.querySelectorAll('input, select, textarea'),
                function (el) { if (!el.checkValidity()) ok = false; }
            );
            if (ok) clearFieldError(field);
        });

        form.addEventListener('keydown', function (event) {
            if (event.key !== 'Enter') return;
            var tag = event.target.tagName;
            if (tag === 'TEXTAREA' || tag === 'BUTTON') return;
            if (tag !== 'INPUT' && tag !== 'SELECT') return;

            event.preventDefault();
            if (validateStep(steps[current])) {
                shake(steps[current]);
                return;
            }
            if (current < total - 1) {
                goTo(current + 1, true);
            } else if (form.requestSubmit) {
                form.requestSubmit(submitBtn || undefined);
            } else {
                form.submit();
            }
        });

        form.addEventListener('submit', function (event) {
            var bad = firstInvalidStep();
            if (bad > -1) {
                event.preventDefault();
                if (bad !== current) goTo(bad, true);
                else { shake(steps[current]); focusStep(); }
                return;
            }
            /* Everything passed: show the bar complete while the POST leaves. */
            answered = answered.map(function () { return true; });
            if (fill) fill.style.width = '100%';
        });

        /* Start on the step carrying the first server-side error, if any. */
        activate(current);
        paintProgress();
    }

    motion.onReady(init);
})(window, document);
