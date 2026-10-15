/*
 * Scrutineer explorer. Vanilla JS, no dependencies, no requests beyond this site's own data files.
 *
 * data/votes.json = { runs: [{id, label}], split: bool, votes: [vote, ...] }, newest vote first.
 * Vote keys (short on purpose, the file carries every answer):
 *   a    vote number (anr), e.g. "665" or "465.1"
 *   d    vote date, ISO 8601
 *   t    {lang: official title}
 *   g    government lost: 1, won: 0, vote not yet held: null
 *   i    instrument          e   era          m   margin bucket          s   people and cantons split: 1
 *   pc   1 for votes not yet held; their outcome question is family F7 instead of F1
 *   o    gold outcome: accepted | rejected | not_decided
 *   f    Federal Council recommendation: accept | reject
 *   y    yes share, percent  cy  cantons yes  cn  cantons no   ic  added to the constitution: yes | no
 *   u    source URLs
 *   k    {family: [lang, ...]} the items that exist for this vote
 *   v    {run: {lang: verdict}} the outcome-question verdicts shown in the table
 *   r    {run: {family: {lang: [response, parser label, grade, grade source, judge reason, status]}}}
 *        When `split` is true, `r` is absent here and fetched from data/votes/<a>.json on expand.
 *
 * URL state: ?lang=fr&gov=lost&inst=initiative&era=1990s&q=text#vote-665
 */
(function () {
  'use strict';

  var LANGS = ['de', 'fr', 'it', 'en', 'rm'];
  var LANG_NAMES = { de: 'German', fr: 'French', it: 'Italian', en: 'English', rm: 'Romansh' };
  var FAMILIES = [
    ['F1', 'Outcome'],
    ['F2', 'Yes share'],
    ['F3', 'Federal Council recommendation'],
    ['F4', 'Majority of cantons'],
    ['F5', 'Outcome from the numbers'],
    ['F6', 'Added to the constitution'],
    ['F7', 'Outcome of a vote not yet held'],
    ['F8', 'One-sentence summary']
  ];
  var INSTRUMENTS = {
    initiative: 'Popular initiative',
    counterproposal: 'Counter-proposal',
    referendum_obligatory: 'Mandatory referendum',
    referendum_optional: 'Optional referendum'
  };
  var MARGINS = { within_5: 'within 5 points', '5_to_15': '5 to 15 points', over_15: 'over 15 points' };
  var OUTCOMES = { accepted: 'accepted', rejected: 'rejected', not_decided: 'not yet held' };
  var VERDICTS = {
    correct: 'correct',
    incorrect: 'incorrect',
    not_attempted: 'abstained',
    failed: 'request failed',
    unjudged: 'awaiting judge',
    ungraded: 'not yet graded',
    missing: 'not yet run'
  };
  var DOTS = { correct: 'dot-correct', incorrect: 'dot-incorrect', not_attempted: 'dot-abstained' };
  var PARSER = {
    accepted: 'accepted', rejected: 'rejected', accept: 'accept', reject: 'reject', yes: 'yes', no: 'no',
    abstain: "I don't know", unparseable: 'unreadable', number: 'number'
  };
  var DEFAULTS = { lang: 'de', gov: 'all', inst: 'all', era: 'all', q: '' };

  var tbody = document.getElementById('votes-body');
  var counter = document.getElementById('count');
  var controls = {
    lang: document.getElementById('f-lang'),
    gov: document.getElementById('f-gov'),
    inst: document.getElementById('f-inst'),
    era: document.getElementById('f-era'),
    q: document.getElementById('f-q')
  };

  var runs = [];
  var votes = [];
  var byAnr = new Map();
  var split = false;
  var answerCache = new Map();
  var state = Object.assign({ open: null }, DEFAULTS);

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (key) {
      if (key === 'text') node.textContent = attrs[key];
      else if (key === 'className') node.className = attrs[key];
      else node.setAttribute(key, attrs[key]);
    });
    (children || []).forEach(function (child) {
      if (child !== null && child !== undefined) node.append(child);
    });
    return node;
  }

  function fold(text) {
    return String(text || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  }

  function allowed(select, value) {
    return Array.prototype.some.call(select.options, function (option) { return option.value === value; });
  }

  function readUrl() {
    var params = new URLSearchParams(location.search);
    var next = { open: null };
    Object.keys(DEFAULTS).forEach(function (key) {
      var value = params.get(key);
      var valid = value !== null && (key === 'q' || allowed(controls[key], value));
      next[key] = valid ? value : DEFAULTS[key];
    });
    var match = location.hash.match(/^#vote-(.+)$/);
    var anr = match ? decodeURIComponent(match[1]) : null;
    next.open = anr && byAnr.has(anr) ? anr : null;
    return next;
  }

  function writeUrl(push) {
    var params = new URLSearchParams();
    Object.keys(DEFAULTS).forEach(function (key) {
      if (state[key] !== DEFAULTS[key]) params.set(key, state[key]);
    });
    var query = params.toString();
    var url = location.pathname + (query ? '?' + query : '') + (state.open ? '#vote-' + state.open : '');
    if (url === location.pathname + location.search + location.hash) return;
    history[push ? 'pushState' : 'replaceState'](null, '', url);
  }

  function syncControls() {
    Object.keys(controls).forEach(function (key) { controls[key].value = state[key]; });
  }

  function title(vote) {
    var langs = [state.lang].concat(LANGS);
    for (var i = 0; i < langs.length; i += 1) {
      if (vote.t[langs[i]]) return { text: vote.t[langs[i]], lang: langs[i] };
    }
    return { text: 'Vote ' + vote.a, lang: state.lang };
  }

  function matches(vote) {
    if (state.gov === 'won' && vote.g !== 0) return false;
    if (state.gov === 'lost' && vote.g !== 1) return false;
    if (state.inst !== 'all' && vote.i !== state.inst) return false;
    if (state.era !== 'all' && vote.e !== state.era) return false;
    if (!state.q) return true;
    var haystack = fold(vote.a + ' ' + Object.keys(vote.t).map(function (k) { return vote.t[k]; }).join(' '));
    return haystack.indexOf(fold(state.q.trim())) !== -1;
  }

  function verdict(code, extra) {
    if (!code) return el('span', { className: 'muted', text: 'not yet run' });
    var dot = DOTS[code];
    var label = (VERDICTS[code] || code) + (extra || '');
    return el('span', { className: dot ? 'verdict ' + dot : 'verdict muted', text: label });
  }

  function tableVerdict(vote, run) {
    var family = vote.pc ? 'F7' : 'F1';
    if ((vote.k[family] || []).indexOf(state.lang) === -1) return el('span', { className: 'muted', text: 'no item' });
    var perLang = vote.v[run.id] || {};
    return verdict(perLang[state.lang]);
  }

  function governmentCell(vote) {
    if (vote.g === 1) return el('span', { className: 'gov-lost', text: 'lost' });
    if (vote.g === 0) return document.createTextNode('won');
    return el('span', { className: 'muted', text: 'not yet held' });
  }

  function row(vote) {
    var shown = title(vote);
    var titleNodes = [el('span', { className: 'anr', text: vote.a }), el('span', { className: 'title', text: shown.text })];
    if (shown.lang !== state.lang) {
      titleNodes.push(el('span', { className: 'fallback', text: LANG_NAMES[shown.lang] + ' title' }));
    }
    var button = el('button', {
      type: 'button', className: 'row-toggle', 'aria-expanded': 'false', 'aria-controls': 'detail-' + vote.a
    }, titleNodes);
    var cells = [
      el('td', { className: 'date', 'data-label': 'Date', text: vote.d || 'n/a' }),
      el('td', { className: 'title-cell', 'data-label': 'Vote' }, [button]),
      el('td', { 'data-label': 'Instrument', text: INSTRUMENTS[vote.i] || 'n/a' }),
      el('td', { 'data-label': 'Government' }, [governmentCell(vote)]),
      el('td', { 'data-label': 'Outcome', text: OUTCOMES[vote.o] || 'n/a' })
    ];
    runs.forEach(function (run) {
      cells.push(el('td', { className: 'verdict-cell', 'data-label': run.label }, [tableVerdict(vote, run)]));
    });
    var tr = el('tr', { className: 'vote', id: 'vote-' + vote.a, 'data-anr': vote.a }, cells);
    tr.addEventListener('click', function (event) {
      if (event.target.closest('a')) return;
      toggle(vote.a);
    });
    return tr;
  }

  function render() {
    var shown = votes.filter(matches);
    var fragment = document.createDocumentFragment();
    shown.forEach(function (vote) { fragment.append(row(vote)); });
    if (!shown.length) {
      var empty = el('td', { colspan: String(5 + runs.length), className: 'empty', text: 'No votes match these filters.' });
      fragment.append(el('tr', {}, [empty]));
    }
    tbody.replaceChildren(fragment);
    counter.textContent = shown.length + ' of ' + votes.length + ' votes';
    syncOpen();
  }

  function goldList(vote) {
    var entries = [['Outcome', OUTCOMES[vote.o] || 'n/a']];
    if (vote.y !== null && vote.y !== undefined) entries.push(['Yes share', Number(vote.y).toFixed(2) + '%']);
    if (vote.cy !== null && vote.cy !== undefined) entries.push(['Cantons', vote.cy + ' yes, ' + vote.cn + ' no']);
    if (vote.f) entries.push(['Federal Council', vote.f === 'accept' ? 'recommended yes' : 'recommended no']);
    entries.push(['Government', vote.g === 1 ? 'lost' : vote.g === 0 ? 'won' : 'not yet held']);
    if (vote.ic) entries.push(['Added to the constitution', vote.ic]);
    if (vote.m) entries.push(['Margin', MARGINS[vote.m] || vote.m]);
    if (vote.s === 1) entries.push(['People and cantons', 'disagreed']);
    entries.push(['Instrument', INSTRUMENTS[vote.i] || 'n/a']);
    var dl = el('dl', { className: 'gold' });
    entries.forEach(function (entry) {
      dl.append(el('div', {}, [el('dt', { text: entry[0] }), el('dd', { text: entry[1] })]));
    });
    return dl;
  }

  function sources(vote) {
    var list = el('ul', { className: 'sources' });
    (vote.u || []).filter(Boolean).forEach(function (url) {
      var host = url;
      try { host = new URL(url).hostname.replace(/^www\./, ''); } catch (error) { host = url; }
      list.append(el('li', {}, [el('a', { href: url, rel: 'noopener', text: host })]));
    });
    return el('div', { className: 'source-block' }, [el('h3', { text: 'Sources' }), list]);
  }

  function answerRow(lang, answer) {
    var cells = [el('td', { className: 'lang', 'data-label': 'Language', text: LANG_NAMES[lang] })];
    if (!answer) {
      cells.push(el('td', { colSpan: '4', 'data-label': 'Answer', className: 'muted', text: 'not yet run' }));
      return el('tr', {}, cells);
    }
    var response = answer[0];
    var text = answer[5] === 'failed' ? el('span', { className: 'muted', text: 'request failed' })
      : el('div', { className: 'answer-text', text: response === null || response === '' ? '(empty)' : response });
    var source = answer[3] ? ' (' + answer[3] + ')' : '';
    cells.push(el('td', { 'data-label': 'Answer' }, [text]));
    cells.push(el('td', { className: 'parsed', 'data-label': 'Parser', text: PARSER[answer[1]] || answer[1] || 'n/a' }));
    cells.push(el('td', { 'data-label': 'Verdict' }, [verdict(answer[2] || answer[5], answer[2] ? source : '')]));
    cells.push(el('td', { className: 'reason', 'data-label': 'Judge reason', text: answer[4] || '' }));
    return el('tr', {}, cells);
  }

  function runSection(vote, run, answers) {
    var heading = el('h3', { text: run.label });
    if (!answers || !Object.keys(answers).length) {
      return el('section', { className: 'run' }, [heading, el('p', { className: 'muted', text: 'not yet run' })]);
    }
    var head = el('thead', {}, [el('tr', {}, ['Language', 'Answer', 'Parser', 'Verdict', 'Judge reason'].map(
      function (name) { return el('th', { scope: 'col', text: name }); }))]);
    var table = el('table', { className: 'answers' }, [
      el('caption', { className: 'visually-hidden', text: run.label + ' answers for vote ' + vote.a }), head
    ]);
    FAMILIES.forEach(function (family) {
      var langs = vote.k[family[0]];
      if (!langs) return;
      var group = el('tbody', {}, [el('tr', { className: 'family' }, [
        el('th', { colSpan: '5', scope: 'rowgroup', text: family[0] + ' ' + family[1] })
      ])]);
      var perLang = answers[family[0]] || {};
      langs.forEach(function (lang) { group.append(answerRow(lang, perLang[lang])); });
      table.append(group);
    });
    return el('section', { className: 'run' }, [heading, table]);
  }

  function fillDetail(container, vote, answersByRun) {
    var parts = [el('div', { className: 'detail-head' }, [goldList(vote), sources(vote)])];
    runs.forEach(function (run) { parts.push(runSection(vote, run, answersByRun[run.id])); });
    container.replaceChildren.apply(container, parts);
  }

  function loadAnswers(vote) {
    if (!split) return Promise.resolve(vote.r || {});
    if (answerCache.has(vote.a)) return Promise.resolve(answerCache.get(vote.a));
    return fetch('data/votes/' + encodeURIComponent(vote.a) + '.json')
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (payload) {
        answerCache.set(vote.a, payload.r || {});
        return payload.r || {};
      });
  }

  function detailRow(vote) {
    var container = el('div', { className: 'detail-body' }, [el('p', { className: 'muted', text: 'Loading answers' })]);
    var td = el('td', { colspan: String(5 + runs.length) }, [container]);
    loadAnswers(vote).then(function (answers) { fillDetail(container, vote, answers); }, function (error) {
      container.replaceChildren(el('p', { text: 'Could not load the answers for this vote: ' + error.message }));
    });
    return el('tr', { className: 'detail', id: 'detail-' + vote.a }, [td]);
  }

  function syncOpen() {
    tbody.querySelectorAll('tr.detail').forEach(function (node) { node.remove(); });
    tbody.querySelectorAll('tr.vote.open').forEach(function (node) {
      node.classList.remove('open');
      node.querySelector('.row-toggle').setAttribute('aria-expanded', 'false');
    });
    if (!state.open) return;
    var tr = document.getElementById('vote-' + state.open);
    if (!tr) return;
    tr.classList.add('open');
    var button = tr.querySelector('.row-toggle');
    button.setAttribute('aria-expanded', 'true');
    tr.after(detailRow(byAnr.get(state.open)));
  }

  function scrollToOpen() {
    var tr = state.open && document.getElementById('vote-' + state.open);
    if (!tr) return;
    tr.scrollIntoView({ block: 'start' });
    tr.querySelector('.row-toggle').focus({ preventScroll: true });
  }

  function toggle(anr) {
    state.open = state.open === anr ? null : anr;
    writeUrl(true);
    syncOpen();
  }

  function onControl(key, push) {
    return function () {
      state[key] = controls[key].value;
      writeUrl(push);
      render();
    };
  }

  function fromUrl() {
    state = readUrl();
    syncControls();
    render();
    scrollToOpen();
  }

  function start(data) {
    runs = data.runs || [];
    votes = data.votes || [];
    split = Boolean(data.split);
    votes.forEach(function (vote) { byAnr.set(vote.a, vote); });
    ['lang', 'gov', 'inst', 'era'].forEach(function (key) {
      controls[key].addEventListener('change', onControl(key, true));
    });
    controls.q.addEventListener('input', onControl('q', false));
    controls.q.form.addEventListener('submit', function (event) { event.preventDefault(); });
    window.addEventListener('popstate', fromUrl);
    window.addEventListener('hashchange', fromUrl);
    fromUrl();
  }

  fetch('data/votes.json')
    .then(function (response) {
      if (!response.ok) throw new Error('HTTP ' + response.status);
      return response.json();
    })
    .then(start)
    .catch(function (error) {
      counter.textContent = 'Could not load data/votes.json: ' + error.message;
    });
})();
