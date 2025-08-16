// app.js
const DATA_URL = '/src2/public/data.json';

// Increment CACHE_VERSION when the data shape or desired content changes.
// This guarantees an immediate refetch and avoids stale caches.
const CACHE_VERSION = 'v1.0.0';
const CACHE_KEY = 'syllabus-cache';
const HASH_KEY = 'syllabus-hash';
const VERSION_KEY = 'syllabus-version';

// Optional background refresh (silent) interval in ms
const BACKGROUND_REFRESH_INTERVAL = 5 * 60 * 1000; // 5 minutes

// State
const state = {
    raw: [],
    courses: [],
    semesters: [],
    filters: {
        semester: '',
        credits: '',
        search: '',
        advanced: '',
        sortBy: 'code',
        sortDir: 'asc',
    },
    openCards: new Set(),
};

const els = {
    search: document.getElementById('search'),
    clearSearch: document.getElementById('clearSearch'),
    advanced: document.getElementById('advancedSearch'),
    semester: document.getElementById('semester'),
    credits: document.getElementById('credits'),
    sortBy: document.getElementById('sortBy'),
    sortDir: document.getElementById('sortDir'),
    clearFilters: document.getElementById('clearFilters'),
    toggleFilters: document.getElementById('toggleFilters'),
    closeFilters: document.getElementById('closeFilters'),
    filtersPanel: document.getElementById('filters'),
    statusText: document.getElementById('statusText'),
    updateBadge: document.getElementById('updateBadge'),
    loading: document.getElementById('loading'),
    error: document.getElementById('error'),
    errorMsg: document.getElementById('errorMsg'),
    retry: document.getElementById('retry'),
    list: document.getElementById('list'),
    empty: document.getElementById('empty'),
    cardTpl: document.getElementById('courseCardTpl'),
};

// Utilities
const debounce = (fn, ms = 200) => {
    let t;
    return (...args) => {
        clearTimeout(t);
        t = setTimeout(() => fn(...args), ms);
    };
};

function normalizeCourse(c) {
    const code = (c.course_code || '').trim();
    const title = (c.title || '').trim() || '(Untitled)';
    const semester = (c.semester || '').trim() || 'N/A';
    const credits = Number.isFinite(c.credits) ? c.credits : (Number(c.credits) || 0);

    const courseType = (c.type || c.course_type || '').trim();
    const group = (c.group || '').trim();
    const prereq = Array.isArray(c.prerequisites) ? c.prerequisites : (c.prerequisites ? [String(c.prerequisites)] : []);
    const examHours = (c.exam_hours || '').toString();

    const cie = c.cie_marks ?? (c.assessment?.cie_marks);
    const ese = c.ese_marks ?? (c.assessment?.ese_marks);

    const objectives = Array.isArray(c.objectives) ? c.objectives : (c.course_objectives || []);

    const modules = Array.isArray(c.modules) ? c.modules.map((m, i) => ({
        module_number: Number.isFinite(m.module_number) ? m.module_number : (Number(m.module_number) || (i + 1)),
        content: Array.isArray(m.content) ? m.content : (m.content ? [String(m.content)] : []),
        contact_hours: m.contact_hours || m.hours || null,
        video_links: Array.isArray(m.video_links) ? m.video_links : [],
    })) : [];

    const outcomes = Array.isArray(c.course_outcomes) ? c.course_outcomes.map(o => ({
        code: (o.code || '').trim() || 'CO',
        description: (o.description || '').trim(),
        knowledge_level: (o.knowledge_level || '').trim().toUpperCase(), // e.g., K1-K6
    })) : [];

    const assessment = c.assessment || {};

    const textbooks = Array.isArray(c.textbooks) ? c.textbooks : [];
    const reference_books = Array.isArray(c.reference_books) ? c.reference_books : [];

    // Build searchable text fields
    const fieldParts = [
        code, title, semester, String(credits), courseType, group,
        prereq.join(' '), objectives.join(' '),
        outcomes.map(o => `${o.code} ${o.knowledge_level} ${o.description}`).join(' '),
        String(c.cie_marks || ''), String(c.ese_marks || ''),
    ];
    const modulesText = modules.map(m => m.content.join(' ')).join(' ');
    const searchable = (fieldParts.join(' ') + ' ' + modulesText).toLowerCase();

    return {
        ...c,
        _norm: {
            code, title, semester, credits, courseType, group, prereq, examHours,
            cie, ese, objectives, modules, outcomes, assessment, textbooks, reference_books,
            searchable, modulesText: modulesText.toLowerCase(),
        }
    };
}

function computeHash(obj) {
    // Simple 32-bit hash of JSON string
    const str = JSON.stringify(obj);
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = ((hash << 5) - hash) + str.charCodeAt(i);
        hash |= 0;
    }
    return hash.toString();
}

// Cache layer
async function fetchData({ bust = false } = {}) {
    const cacheVersion = localStorage.getItem(VERSION_KEY);
    const cached = localStorage.getItem(CACHE_KEY);

    if (!bust && cacheVersion === CACHE_VERSION && cached) {
        try {
            const json = JSON.parse(cached);
            return { json, fromCache: true };
        } catch { /* fallthrough to network */ }
    }
    const res = await fetch(DATA_URL, { cache: 'no-cache' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const json = await res.json();

    // Save with new version and hash
    localStorage.setItem(CACHE_KEY, JSON.stringify(json));
    localStorage.setItem(VERSION_KEY, CACHE_VERSION);
    localStorage.setItem(HASH_KEY, computeHash(json));

    return { json, fromCache: false };
}

// Background update without losing state
async function backgroundRefresh() {
    try {
        const res = await fetch(DATA_URL, { cache: 'no-cache' });
        if (!res.ok) return;
        const fresh = await res.json();
        const freshHash = computeHash(fresh);
        const oldHash = localStorage.getItem(HASH_KEY);
        if (freshHash !== oldHash) {
            localStorage.setItem(CACHE_KEY, JSON.stringify(fresh));
            localStorage.setItem(HASH_KEY, freshHash);
            // Re-normalize and re-render but preserve UI state
            loadFromCacheAndRender({ silentUpdate: true });
        }
    } catch { /* ignore */ }
}

function loadFromCacheAndRender({ silentUpdate = false } = {}) {
    const cached = localStorage.getItem(CACHE_KEY);
    if (!cached) return;
    try {
        const json = JSON.parse(cached);
        const normalized = (json.courses || []).map(normalizeCourse);
        state.raw = json.courses || [];
        state.courses = normalized;
        setSemesters(normalized);
        render();
        if (!silentUpdate) {
            showBadge('Loaded from cache');
        } else {
            showBadge('Updated');
        }
    } catch { /* ignore */ }
}

// UI helpers
function showSection(el) {
    els.loading.classList.add('hidden');
    els.error.classList.add('hidden');
    els.empty.classList.add('hidden');
    el.classList.remove('hidden');
}

function setStatus(text) {
    els.statusText.textContent = text;
}

function showBadge(text) {
    els.updateBadge.textContent = text;
    els.updateBadge.classList.remove('hidden');
    setTimeout(() => els.updateBadge.classList.add('hidden'), 2200);
}

function setSemesters(courses) {
    const uniq = Array.from(new Set(courses.map(c => c._norm.semester))).filter(Boolean).sort();
    // Preserve "All semesters" option
    const current = els.semester.value;
    els.semester.innerHTML = '<option value="">All semesters</option>' + uniq.map(s => `<option value="${s}">${s}</option>`).join('');
    if (uniq.includes(current)) els.semester.value = current;
}

// Rendering
function render() {
    const filtered = applyFilters();
    els.list.innerHTML = '';
    if (!filtered.length) {
        setStatus('0 courses');
        showSection(els.empty);
        return;
    }
    setStatus(`${filtered.length} ${filtered.length === 1 ? 'course' : 'courses'}`);
    filtered.forEach(course => {
        const node = renderCourseCard(course);
        els.list.appendChild(node);
    });
    showSection(els.list);
}

function renderCourseCard(course) {
    const tpl = els.cardTpl.content.cloneNode(true);
    const article = tpl.querySelector('article');
    const toggle = tpl.querySelector('.card-toggle');
    const body = tpl.querySelector('.card-body');

    const id = `detail-${course._norm.code || course._norm.title}`.toLowerCase().replace(/[^a-z0-9]+/g, '-');
    article.dataset.code = course._norm.code;
    toggle.setAttribute('aria-controls', id);
    body.id = id;

    tpl.querySelector('.code').textContent = course._norm.code || '—';
    tpl.querySelector('.title').textContent = course._norm.title;
    const semTag = tpl.querySelector('.semester');
    semTag.textContent = course._norm.semester;
    const crTag = tpl.querySelector('.credits');
    crTag.textContent = `${course._norm.credits} credits`;

    const typeTag = tpl.querySelector('.tag.type');
    if (course._norm.courseType) {
        typeTag.textContent = course._norm.courseType;
        typeTag.classList.remove('hidden');
    }

    const isOpen = state.openCards.has(course._norm.code);
    article.dataset.open = isOpen ? 'true' : 'false';
    toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');

    body.appendChild(renderCourseDetail(course));

    toggle.addEventListener('click', () => {
        const nowOpen = article.dataset.open !== 'true';
        article.dataset.open = nowOpen ? 'true' : 'false';
        toggle.setAttribute('aria-expanded', nowOpen ? 'true' : 'false');
        if (nowOpen) state.openCards.add(course._norm.code);
        else state.openCards.delete(course._norm.code);
    });

    return tpl;
}

function renderCourseDetail(course) {
    const container = document.createElement('div');
    container.className = 'detail-grid';

    // Basic info
    const info = document.createElement('div');
    info.className = 'detail-row';
    info.innerHTML = `
    <div><span class="key">Code:</span> ${escapeHtml(course._norm.code || '—')}</div>
    <div><span class="key">Title:</span> ${escapeHtml(course._norm.title)}</div>
    <div><span class="key">Group:</span> ${escapeHtml(course._norm.group || '—')}</div>
    <div><span class="key">Type:</span> ${escapeHtml(course._norm.courseType || '—')}</div>
    <div><span class="key">Semester:</span> ${escapeHtml(course._norm.semester)}</div>
    <div><span class="key">Credits:</span> ${course._norm.credits}</div>
    <div><span class="key">Prerequisites:</span> ${escapeHtml(course._norm.prereq.join('; ') || '—')}</div>
    <div><span class="key">Exam hours:</span> ${escapeHtml(course._norm.examHours || '—')}</div>
    <div><span class="key">CIE marks:</span> ${course._norm.cie ?? '—'}</div>
    <div><span class="key">ESE marks:</span> ${course._norm.ese ?? '—'}</div>
  `;
    container.appendChild(info);

    // Teaching hours breakdown if present
    const th = course.teaching_hours || course.teachingHours || course['LTP'] || course['hours'];
    if (th && (th.lecture || th.tutorial || th.practical)) {
        const table = document.createElement('table');
        table.innerHTML = `
      <thead><tr><th>Lecture</th><th>Tutorial</th><th>Practical</th><th>Total</th></tr></thead>
      <tbody>
        <tr>
          <td>${th.lecture ?? '—'}</td>
          <td>${th.tutorial ?? '—'}</td>
          <td>${th.practical ?? '—'}</td>
          <td>${(th.lecture || 0) + (th.tutorial || 0) + (th.practical || 0)}</td>
        </tr>
      </tbody>
    `;
        container.appendChild(table);
    }

    // Objectives
    if (course._norm.objectives.length) {
        const obj = document.createElement('div');
        obj.innerHTML = `<h3>Course objectives</h3>`;
        const ul = document.createElement('ul');
        ul.style.margin = '8px 0 0 16px';
        course._norm.objectives.forEach(o => {
            const li = document.createElement('li');
            li.textContent = o;
            ul.appendChild(li);
        });
        obj.appendChild(ul);
        container.appendChild(obj);
    }

    // Modules
    if (course._norm.modules.length) {
        const modWrap = document.createElement('div');
        modWrap.innerHTML = `<h3>Modules</h3>`;
        course._norm.modules.forEach((m, idx) => {
            const det = document.createElement('details');
            det.className = 'module';
            if (idx === 0) det.open = true;
            const summary = document.createElement('summary');
            const modNo = m.module_number ?? (idx + 1);
            summary.innerHTML = `<strong>Module ${modNo}</strong> ${m.contact_hours ? `<span class="muted">• ${m.contact_hours} hours</span>` : ''}`;
            det.appendChild(summary);
            const content = document.createElement('div');
            content.className = 'content';
            const list = document.createElement('ul');
            list.style.margin = '8px 0 0 16px';
            (m.content || []).forEach(line => {
                const li = document.createElement('li');
                li.textContent = line;
                list.appendChild(li);
            });
            content.appendChild(list);

            // Video links per module
            if (m.video_links && m.video_links.length) {
                const vids = document.createElement('div');
                vids.style.marginTop = '8px';
                vids.innerHTML = `<div class="muted" style="margin-bottom:6px;">Video links</div>`;
                const vlist = document.createElement('ul');
                vlist.style.margin = '0 0 0 16px';
                m.video_links.forEach(v => {
                    const li = document.createElement('li');
                    const a = document.createElement('a');
                    a.href = v.url || v; a.target = '_blank'; a.rel = 'noopener noreferrer';
                    a.textContent = v.title || v.url || v;
                    li.appendChild(a);
                    vlist.appendChild(li);
                });
                vids.appendChild(vlist);
                content.appendChild(vids);
            }

            det.appendChild(content);
            modWrap.appendChild(det);
        });
        container.appendChild(modWrap);
    }

    // Assessment structure (CIE/ESE)
    const asmt = course._norm.assessment || {};
    if (asmt.cie || asmt.CIE || asmt.cie_breakdown || asmt.cieMarks) {
        const cie = asmt.cie || asmt.cie_breakdown || asmt.CIE || [];
        const cieDiv = document.createElement('div');
        cieDiv.innerHTML = `<h3>CIE breakdown</h3>`;
        const table = document.createElement('table');
        const rows = Array.isArray(cie) ? cie : [];
        table.innerHTML = `
      <thead><tr><th>Component</th><th>Marks</th><th>Weight</th></tr></thead>
      <tbody>${rows.map(r => `
        <tr><td>${escapeHtml(r.component || r.name || '—')}</td><td>${r.marks ?? '—'}</td><td>${r.weight ?? '—'}</td></tr>
      `).join('')}</tbody>`;
        cieDiv.appendChild(table);
        container.appendChild(cieDiv);
    }

    if (asmt.ese || asmt.ESE || asmt.ese_breakdown || asmt.eseMarks || course._norm.ese != null) {
        const eseRaw = asmt.ese || asmt.ese_breakdown || asmt.ESE || {};
        const eseDiv = document.createElement('div');
        eseDiv.innerHTML = `<h3>ESE breakdown</h3>`;
        const table = document.createElement('table');
        const rows = Array.isArray(eseRaw.items) ? eseRaw.items : (Array.isArray(eseRaw) ? eseRaw : []);
        const total = eseRaw.total ?? course._norm.ese ?? '';
        const desc = eseRaw.description || '';
        table.innerHTML = `
      <thead><tr><th>Component</th><th>Marks</th><th>Weight</th></tr></thead>
      <tbody>${rows.map(r => `
        <tr><td>${escapeHtml(r.component || r.name || '—')}</td><td>${r.marks ?? '—'}</td><td>${r.weight ?? '—'}</td></tr>
      `).join('')}
      ${total !== '' ? `<tr><td><strong>Total</strong></td><td colspan="2"><strong>${total}</strong>${desc ? ` — ${escapeHtml(desc)}` : ''}</td></tr>` : ''}
      </tbody>`;
        eseDiv.appendChild(table);
        container.appendChild(eseDiv);
    }

    // Course outcomes with Bloom's badges
    if (course._norm.outcomes.length) {
        const co = document.createElement('div');
        co.innerHTML = `<h3>Course outcomes</h3>`;
        const list = document.createElement('ul');
        list.style.margin = '8px 0 0 16px';
        course._norm.outcomes.forEach(o => {
            const li = document.createElement('li');
            const badge = document.createElement('span');
            badge.className = 'kbadge';
            const level = (o.knowledge_level || '').match(/K[1-6]/)?.[0] || 'K?';
            badge.textContent = level;
            li.appendChild(badge);
            const text = document.createElement('span');
            text.style.marginLeft = '8px';
            text.textContent = `${o.code}: ${o.description}`;
            li.appendChild(text);
            list.appendChild(li);
        });
        co.appendChild(list);
        container.appendChild(co);
    }

    // Books
    if (course._norm.textbooks.length) {
        const tb = document.createElement('div');
        tb.innerHTML = `<h3>Textbooks</h3>`;
        const ul = document.createElement('ul');
        ul.style.margin = '8px 0 0 16px';
        course._norm.textbooks.forEach(t => {
            const li = document.createElement('li');
            li.textContent = typeof t === 'string' ? t : [t.title, t.author, t.publisher, t.year].filter(Boolean).join(', ');
            ul.appendChild(li);
        });
        tb.appendChild(ul);
        container.appendChild(tb);
    }
    if (course._norm.reference_books.length) {
        const rb = document.createElement('div');
        rb.innerHTML = `<h3>Reference books</h3>`;
        const ul = document.createElement('ul');
        ul.style.margin = '8px 0 0 16px';
        course._norm.reference_books.forEach(t => {
            const li = document.createElement('li');
            li.textContent = typeof t === 'string' ? t : [t.title, t.author, t.publisher, t.year].filter(Boolean).join(', ');
            ul.appendChild(li);
        });
        rb.appendChild(ul);
        container.appendChild(rb);
    }

    return container;
}

function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));
}

// Filtering and sorting
function applyFilters() {
    const f = state.filters;
    const search = f.search.trim().toLowerCase();
    const adv = f.advanced.trim().toLowerCase();

    let out = state.courses.filter(c => {
        if (f.semester && c._norm.semester !== f.semester) return false;
        if (f.credits !== '' && String(c._norm.credits) !== String(f.credits)) return false;
        if (search && !c._norm.searchable.includes(search)) return false;
        if (adv && !c._norm.modulesText.includes(adv)) return false;
        return true;
    });

    const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });

    const sorters = {
        code: (a, b) => collator.compare(a._norm.code, b._norm.code),
        title: (a, b) => collator.compare(a._norm.title, b._norm.title),
        semester: (a, b) => collator.compare(a._norm.semester, b._norm.semester),
        credits: (a, b) => a._norm.credits - b._norm.credits,
    };
    out.sort(sorters[f.sortBy] || sorters.code);
    if (f.sortDir === 'desc') out.reverse();

    return out;
}

// Events
function bindEvents() {
    els.search.addEventListener('input', debounce(e => {
        state.filters.search = e.target.value;
        render();
    }, 120));

    els.clearSearch.addEventListener('click', () => {
        els.search.value = '';
        state.filters.search = '';
        render();
        els.search.focus();
    });

    els.advanced.addEventListener('input', debounce(e => {
        state.filters.advanced = e.target.value;
        render();
    }, 150));

    els.semester.addEventListener('change', e => {
        state.filters.semester = e.target.value;
        render();
    });

    els.credits.addEventListener('change', e => {
        state.filters.credits = e.target.value;
        render();
    });

    els.sortBy.addEventListener('change', e => {
        state.filters.sortBy = e.target.value;
        render();
    });

    els.sortDir.addEventListener('click', () => {
        state.filters.sortDir = state.filters.sortDir === 'asc' ? 'desc' : 'asc';
        // Rotate icon for affordance
        els.sortDir.style.transform = state.filters.sortDir === 'desc' ? 'scaleY(-1)' : 'none';
        render();
    });

    els.clearFilters.addEventListener('click', () => {
        els.semester.value = '';
        els.credits.value = '';
        els.search.value = '';
        els.advanced.value = '';
        state.filters = { semester: '', credits: '', search: '', advanced: '', sortBy: 'code', sortDir: 'asc' };
        render();
    });

    // Filters panel on mobile
    const setFiltersOpen = (open) => {
        els.filtersPanel.classList.toggle('open', open);
        els.toggleFilters.setAttribute('aria-expanded', open ? 'true' : 'false');
    };
    els.toggleFilters.addEventListener('click', () => {
        const open = !els.filtersPanel.classList.contains('open');
        setFiltersOpen(open);
    });
    els.closeFilters.addEventListener('click', () => setFiltersOpen(false));

    // Retry
    els.retry.addEventListener('click', async () => {
        showSection(els.loading);
        try {
            await init({ forceNetwork: true });
        } catch (err) {
            els.errorMsg.textContent = String(err.message || err);
            showSection(els.error);
        }
    });

    // Persist open cards across rerenders by code already handled via state.openCards
    // Optional: restore focus to main content on route changes
}

async function init({ forceNetwork = false } = {}) {
    try {
        const { json, fromCache } = await fetchData({ bust: forceNetwork });
        const normalized = (json.courses || []).map(normalizeCourse);
        state.raw = json.courses || [];
        state.courses = normalized;

        setSemesters(normalized);
        render();

        setStatus(`${state.courses.length} courses${fromCache ? ' • cache' : ''}`);

        // Kick off background checker
        setInterval(backgroundRefresh, BACKGROUND_REFRESH_INTERVAL);
        // Also run an immediate background check to pick up changes if CACHE_VERSION unchanged
        backgroundRefresh();
    } catch (err) {
        els.errorMsg.textContent = String(err.message || err);
        showSection(els.error);
    }
}

// Boot
document.addEventListener('DOMContentLoaded', async () => {
    showSection(els.loading);
    // Try quick load from cache if version matches; then fetch in background
    const versionMatches = localStorage.getItem(VERSION_KEY) === CACHE_VERSION;
    const hasCache = !!localStorage.getItem(CACHE_KEY);
    if (versionMatches && hasCache) {
        loadFromCacheAndRender();
        // Background fetch to validate and update silently
        backgroundRefresh();
    } else {
        await init();
    }
    bindEvents();
});