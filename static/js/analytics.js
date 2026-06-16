(function() {
    function send(endpoint, data) {
        try {
            if (navigator.sendBeacon) {
                navigator.sendBeacon(endpoint, JSON.stringify(data));
            } else {
                var xhr = new XMLHttpRequest();
                xhr.open('POST', endpoint, true);
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.send(JSON.stringify(data));
            }
        } catch (e) {}
    }

    send('/track/pageview', { page: window.location.pathname });

    var sections = document.querySelectorAll('section[id]');
    if (sections.length && 'IntersectionObserver' in window) {
        var observed = {};
        var observer = new IntersectionObserver(function(entries) {
            entries.forEach(function(entry) {
                if (entry.isIntersecting && !observed[entry.target.id]) {
                    observed[entry.target.id] = true;
                    send('/track/interest', {
                        section: entry.target.id,
                        action: 'view'
                    });
                }
            });
        }, { threshold: 0.4 });
        sections.forEach(function(s) { observer.observe(s); });
    }

    document.addEventListener('click', function(e) {
        var link = e.target.closest('a[href]');
        if (!link) return;
        var href = link.getAttribute('href');
        if (href && (href.startsWith('http') || href.startsWith('//'))) {
            var section = link.closest('section');
            send('/track/interest', {
                section: section ? section.id : 'unknown',
                action: 'click',
                target: href
            });
        }
    });
})();
