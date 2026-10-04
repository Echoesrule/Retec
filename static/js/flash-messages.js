(function () {
    'use strict';

    var messages = document.querySelectorAll('.flash, .admin-flash');

    messages.forEach(function (message) {
        window.setTimeout(function () {
            if (!message.isConnected) return;
            message.classList.add('is-dismissing');
            window.setTimeout(function () {
                if (message.isConnected) message.remove();
            }, 300);
        }, 6000);
    });
})();