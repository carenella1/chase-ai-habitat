// Global "what does this mean" tooltip engine.
// Any element with class="info-dot" and data-tip-title / data-tip-body
// (optionally data-tip-link + data-tip-link-text) gets a hover/focus popup.
// Rendered into one fixed-position element appended to <body> so it's never
// clipped by a panel's overflow:hidden.
(function () {
    let tip;
    let activeDot = null;
    let hideTimer = null;

    function ensureTip() {
        if (tip) return tip;
        tip = document.createElement('div');
        tip.id = 'nex-tooltip';
        document.body.appendChild(tip);
        tip.addEventListener('mouseenter', () => clearTimeout(hideTimer));
        tip.addEventListener('mouseleave', scheduleHide);
        return tip;
    }

    function render(dot) {
        const title = dot.dataset.tipTitle || '';
        const body = dot.dataset.tipBody || '';
        const link = dot.dataset.tipLink || '';
        const linkText = dot.dataset.tipLinkText || 'See how this fits the bigger picture →';
        const t = ensureTip();
        t.innerHTML =
            (title ? `<div class="nt-title">${title}</div>` : '') +
            `<div class="nt-body">${body}</div>` +
            (link ? `<a class="nt-link" href="${link}">${linkText}</a>` : '');
    }

    function position(dot) {
        const t = ensureTip();
        const r = dot.getBoundingClientRect();
        const margin = 10;
        // Measure after content is set (visible but not yet positioned correctly is fine, offscreen measure)
        t.style.left = '0px';
        t.style.top = '0px';
        const tw = t.offsetWidth || 300;
        const th = t.offsetHeight || 60;

        let left = r.left + r.width / 2 - tw / 2;
        left = Math.max(margin, Math.min(left, window.innerWidth - tw - margin));

        let top = r.bottom + 8;
        if (top + th > window.innerHeight - margin) {
            top = r.top - th - 8; // flip above if it would overflow the bottom
        }
        top = Math.max(margin, top);

        t.style.left = `${left}px`;
        t.style.top = `${top}px`;
    }

    function show(dot) {
        clearTimeout(hideTimer);
        activeDot = dot;
        dot.classList.add('info-dot-active');
        render(dot);
        const t = ensureTip();
        t.classList.add('visible');
        position(dot);
    }

    function scheduleHide() {
        clearTimeout(hideTimer);
        hideTimer = setTimeout(() => {
            if (tip) tip.classList.remove('visible');
            if (activeDot) activeDot.classList.remove('info-dot-active');
            activeDot = null;
        }, 120);
    }

    function bind(dot) {
        if (dot.dataset.tipBound) return;
        dot.dataset.tipBound = '1';
        if (!dot.hasAttribute('tabindex')) dot.setAttribute('tabindex', '0');
        dot.addEventListener('mouseenter', () => show(dot));
        dot.addEventListener('mouseleave', scheduleHide);
        dot.addEventListener('focus', () => show(dot));
        dot.addEventListener('blur', scheduleHide);
    }

    function scan() {
        document.querySelectorAll('.info-dot').forEach(bind);
    }

    document.addEventListener('DOMContentLoaded', scan);
    // Pages here poll their own APIs and rebuild panel innerHTML on intervals,
    // which can introduce new .info-dot nodes after load — rescan periodically.
    setInterval(scan, 4000);
    window.addEventListener('scroll', () => activeDot && position(activeDot), true);
    window.addEventListener('resize', () => activeDot && position(activeDot));
})();
