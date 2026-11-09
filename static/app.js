'use strict';

const $ = (id) => document.getElementById(id);
const escapeHTML = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state = {ids: [], talks: new Map(), searchController: null, agendaVersion: 0, query: '', searchResults: [], searchTotal: 0};
try {
  const stored = JSON.parse(localStorage.getItem('righttalk-agenda') || '[]');
  if (Array.isArray(stored)) state.ids = [...new Set(stored.filter((id) => typeof id === 'string'))].slice(0, 100);
} catch (_) { /* Private browsing or a stale value should not break planning. */ }

function notify(message, error = false) {
  $('notice').textContent = message;
  $('notice').className = `notice${error ? ' error' : ''}`;
  $('notice').hidden = false;
}

function persist() {
  try { localStorage.setItem('righttalk-agenda', JSON.stringify(state.ids)); }
  catch (_) { notify('Your agenda is available for this visit. This browser could not save it for next time.'); }
}

function remember(talks) {
  talks.forEach((talk) => state.talks.set(talk.id, {...state.talks.get(talk.id), ...talk}));
}

function filters() {
  return {track: $('track').value || undefined, level: $('level').value || undefined, captioned_only: $('captioned').checked, mode: $('search-mode').value};
}

function setSource(data) {
  const fallback = data.source === 'fallback';
  const timing = Number.isFinite(data.took_ms) ? `${Math.round(data.took_ms)}ms` : '';
  const total = Number.isFinite(data.total) ? `${data.total} results` : '';
  $('source').textContent = fallback ? 'Fallback · Elasticsearch unavailable' : data.source === 'elasticsearch' ? ['Elasticsearch', timing, total].filter(Boolean).join(' · ') : 'Search source unavailable';
  $('source').className = `source-pill${fallback ? ' warning' : ''}`;
  $('latency').textContent = '';
  $('search-method').textContent = data.mode === 'hybrid' ? 'Hybrid · meaning + words' : 'Keyword search';
  $('search-method').className = `method-pill${data.degraded_reason ? ' warning' : ''}`;
  $('search-mode-note').textContent = data.degraded_reason || '';
  $('search-mode-note').hidden = !data.degraded_reason;
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  let body;
  try { body = await response.json(); }
  catch (_) { throw new Error('The server returned an unreadable response. Please try again.'); }
  if (!response.ok) {
    const message = typeof body.detail === 'string' ? body.detail : Array.isArray(body.detail) ? body.detail.map((item) => item.msg).join('; ') : 'The request could not be completed. Please try again.';
    throw new Error(message);
  }
  return body;
}

const post = (path, data) => api(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
function renderSearchResults(talks, reset = true, total = talks.length) {
  if (reset) { state.searchResults = talks; state.searchTotal = total; }
  else state.searchResults.push(...talks);
  const visible = state.searchResults;
  $('talks').innerHTML = visible.length ? visible.map(talkCard).join('') : '<div class="empty-results">No talks found for this combination.<br>Try a broader topic or relax a filter.</div>';
  if (visible.length < state.searchTotal) {
    const more = document.createElement('button');
    more.type = 'button'; more.className = 'show-more';
    more.textContent = `Load ${Math.min(24, state.searchTotal - visible.length)} more (${visible.length} of ${state.searchTotal})`;
    more.addEventListener('click', () => loadMore(more));
    $('talks').appendChild(more);
  }
  $('result-count').textContent = visible.length < state.searchTotal
    ? `${visible.length} of ${state.searchTotal} talks` : `${state.searchTotal} talk${state.searchTotal === 1 ? '' : 's'}`;
}
function updateFacets(facets = {}) {
  for (const [id, name] of [['track', 'track'], ['level', 'level']]) {
    const counts = new Map((facets[name] || []).map((item) => [String(item.key), item.doc_count]));
    [...$(id).options].forEach((option) => {
      if (!option.value) return;
      const base = option.dataset.baseLabel || option.textContent.replace(/ \(\d+\)$/, '');
      option.dataset.baseLabel = base;
      option.textContent = `${base} (${counts.get(option.value) || 0})`;
    });
  }
  const captioned = (facets.captioned || []).find((item) => item.key === true);
  $('captioned-count').textContent = `Captioned only (${captioned?.doc_count || 0})`;
}
async function loadMore(button) {
  button.disabled = true; button.textContent = 'Loading more talks…';
  const params = new URLSearchParams({q:state.query, limit:'24', offset:String(state.searchResults.length)});
  Object.entries(filters()).forEach(([key,value]) => { if (value !== undefined) params.set(key,value); });
  try {
    const data = await api(`/api/search?${params}`);
    remember(data.talks); renderSearchResults(data.talks, false, data.total); updateFacets(data.facets); setSource(data);
  } catch (error) { button.disabled = false; button.textContent = 'More talks failed to load · retry'; notify(error.message, true); }
}
async function loadPlaces(category) {
  $('venue-places').setAttribute('aria-busy', 'true');
  $('venue-places').innerHTML = '<p>Searching Elasticsearch for nearby places…</p>';
  document.querySelectorAll('[data-place-category]').forEach((chip) => {
    const active = chip.dataset.placeCategory === category;
    chip.classList.toggle('active', active); chip.setAttribute('aria-pressed', String(active));
  });
  try {
    const data = await api(`/api/places?category=${encodeURIComponent(category)}&radius_m=1000`);
    $('venue-source').textContent = `Elasticsearch geo search · ${data.total} places${data.data_note === 'curated OSM fallback' ? ' · OSM fallback data' : ''}`;
    const cards = data.places.map((place) => {
      const categoryName = place.category[0].toUpperCase() + place.category.slice(1);
      const distance = place.distance_m >= 1000 ? `${(place.distance_m / 1000).toFixed(1)} km` : `${place.distance_m} m`;
      const osm = `https://www.openstreetmap.org/?mlat=${encodeURIComponent(place.lat)}&mlon=${encodeURIComponent(place.lon)}#map=18/${encodeURIComponent(place.lat)}/${encodeURIComponent(place.lon)}`;
      return `<article class="place-card"><div class="place-title"><h3>${escapeHTML(place.name)}</h3><span class="place-category">${escapeHTML(categoryName)}</span></div><p class="place-distance">${distance} · about ${place.walking_minutes} min walk</p>${place.address ? `<p class="place-address">${escapeHTML(place.address)}</p>` : ''}<a href="${osm}" target="_blank" rel="noreferrer">Open in OpenStreetMap ↗</a></article>`;
    });
    $('venue-places').innerHTML = cards.length ? cards.join('') : '<p class="venue-empty">No listed places in this category within 1 km.</p>';
  } catch (error) {
    $('venue-source').textContent = 'Venue search unavailable';
    $('venue-places').innerHTML = `<p class="venue-empty">${escapeHTML(error.message)}</p>`;
  } finally { $('venue-places').setAttribute('aria-busy', 'false'); }
}
const time = (value) => new Intl.DateTimeFormat('en-US', {hour:'numeric',minute:'2-digit',timeZone:'America/Denver'}).format(new Date(value));
const range = (talk) => `${time(talk.start)} – ${time(talk.end)}`;

function esHighlight(talk, field, fallback) {
  const fragment = talk.highlights?.[field]?.[0];
  if (!fragment) return escapeHTML(fallback);
  // Escape the full server fragment, then restore only the explicitly
  // configured <mark> tags. All other markup stays inert text.
  return escapeHTML(fragment).replaceAll('&lt;mark&gt;', '<mark>').replaceAll('&lt;/mark&gt;', '</mark>');
}

function speakerAvatar(name) {
  const initials = name.trim().split(/\s+/).map((part) => [...part][0]).slice(0, 2).join('').toUpperCase();
  let hash = 0;
  for (const char of name) hash = (hash * 31 + char.codePointAt(0)) >>> 0;
  const colors = ['#254e3d', '#48623b', '#526b45'];
  return `<span class="speaker-avatar" aria-hidden="true" style="background:${colors[hash % colors.length]}">${escapeHTML(initials)}</span>`;
}

function accessNotes(talk) {
  const access = talk.accessibility || {};
  const notes = [access.captioned === true ? 'CC · Captioned' : access.captioned === false ? 'No captions' : 'Captions not listed', access.step_free === true ? 'Step-free access' : access.step_free === false ? 'Not step-free' : 'Step-free not listed', access.plain_language_summary === true ? 'Plain-language summary' : access.plain_language_summary === false ? 'No plain-language summary' : 'Summary not listed'];
  return notes.map((note) => `<span>${escapeHTML(note)}</span>`).join('');
}

function talkCard(talk) {
  const selected = state.ids.includes(talk.id);
  return `<article class="talk-card"><div class="talk-top"><span class="time-chip">${escapeHTML(range(talk))}</span><div class="talk-badges"><span class="track-tag ${escapeHTML(talk.track.toLowerCase())}">${escapeHTML(talk.track)}</span><span class="talk-level">${escapeHTML(talk.level)}</span></div></div><h3>${esHighlight(talk, 'title', talk.title)}</h3><p class="talk-origin ${talk.dataset ? 'official' : 'sample'}">${talk.dataset ? 'KubeCon NA 2026 · official session' : 'Illustrative demo sample'}</p><p class="speaker">${speakerAvatar(talk.speaker)}<span>${escapeHTML(talk.speaker)}</span></p><p class="talk-description">${esHighlight(talk, 'description', talk.description)}</p><div class="talk-meta"><span>◷ ${escapeHTML(range(talk))}</span><span>⌖ ${escapeHTML(talk.room)}</span>${talk.source_url ? `<a href="${escapeHTML(talk.source_url)}" target="_blank" rel="noreferrer">Official listing ↗</a>` : ''}</div><div class="talk-bottom"><div class="accessibility" aria-label="Accessibility">${accessNotes(talk)}</div><button type="button" class="add-button${selected ? ' selected' : ''}" data-add="${escapeHTML(talk.id)}" aria-label="${selected ? 'Remove' : 'Add'} ${escapeHTML(talk.title)} ${selected ? 'from' : 'to'} agenda">${selected ? '✓ Added' : '+ Add to day'}</button></div><div class="match-tools"><button type="button" class="explain-button" data-explain="${escapeHTML(talk.id)}" aria-expanded="false">Why this match? <span aria-hidden="true">✧</span></button><div class="match-explanation" role="status" aria-live="polite" hidden></div></div></article>`;
}

async function search() {
  state.searchController?.abort();
  const controller = new AbortController();
  state.searchController = controller;
  $('talks').setAttribute('aria-busy', 'true');
  $('result-count').textContent = 'Finding your talks…';
  const params = new URLSearchParams({q: $('query').value.trim(), limit:'24', offset:'0'});
  Object.entries(filters()).forEach(([key, value]) => { if (value !== undefined) params.set(key, value); });
  try {
    const data = await api(`/api/search?${params}`, {signal:controller.signal});
    if (controller !== state.searchController) return;
    remember(data.talks);
    state.query = params.get('q');
    renderSearchResults(data.talks, true, data.total);
    updateFacets(data.facets);
    setSource(data);
  } catch (error) {
    if (error.name === 'AbortError') return;
    $('result-count').textContent = 'Search unavailable';
    $('talks').innerHTML = '<div class="empty-results">We couldn’t load the program. Check the server connection, then search again.</div>';
    notify(error.message, true);
  } finally {
    if (controller === state.searchController) $('talks').setAttribute('aria-busy', 'false');
  }
}

function updateCardButtons() {
  document.querySelectorAll('[data-add]').forEach((button) => {
    const selected = state.ids.includes(button.dataset.add);
    const title = state.talks.get(button.dataset.add)?.title || 'talk';
    button.classList.toggle('selected', selected);
    button.textContent = selected ? '✓ Added' : '+ Add to day';
    button.setAttribute('aria-label', `${selected ? 'Remove' : 'Add'} ${title} ${selected ? 'from' : 'to'} agenda`);
  });
}

function renderAgenda(talks, clashes = []) {
  $('agenda-count').textContent = String(talks.length);
  $('clear-agenda').disabled = talks.length === 0;
  $('check-agenda').disabled = talks.length === 0;
  $('agenda-status').textContent = talks.length === 0 ? 'Your day is a blank canvas.' : clashes.length ? `${clashes.length} clash${clashes.length === 1 ? '' : 'es'} to resolve · ${talks.length} talks saved` : `${talks.length} talk${talks.length === 1 ? '' : 's'} saved · No clashes. All yours.`;
  $('agenda-talks').innerHTML = talks.length ? talks.map((talk) => `<article class="agenda-item"><div class="agenda-time"><span>${escapeHTML(range(talk))}</span><button class="remove-button" type="button" data-remove="${escapeHTML(talk.id)}" aria-label="Remove ${escapeHTML(talk.title)}">×</button></div><h3>${escapeHTML(talk.title)}</h3>${talk.reason ? `<p class="reason">Why: ${escapeHTML(talk.reason)}</p>` : ''}<p class="room">${escapeHTML(talk.room)} · ${escapeHTML(talk.track)}</p></article>`).join('') : '<div class="empty-agenda"><span class="empty-symbol" aria-hidden="true">↗</span>Add a talk that catches your eye,<br>or let your interests build the day.</div>';
  updateCardButtons();
}

function renderConflicts(data) {
  const conflicted = [...new Set(data.clashes.flatMap((clash) => clash.talk_ids))];
  $('conflicts').innerHTML = conflicted.map((id) => {
    const talk = state.talks.get(id);
    const alternatives = data.alternatives?.[id] || [];
    remember(alternatives);
    return `<div class="conflict"><h3>Time clash</h3><p>“${escapeHTML(talk?.title || id)}” overlaps another saved talk.</p>${alternatives.length ? '<p>Replace it with a related talk that fits:</p>' + alternatives.map((alternative) => `<button type="button" class="alternative" data-replace="${escapeHTML(id)}" data-with="${escapeHTML(alternative.id)}">Swap to this instead — ${escapeHTML(alternative.title)} · ${escapeHTML(range(alternative))}</button>`).join('') : '<p>No compatible alternative found. Remove this talk or the overlapping session.</p>'}</div>`;
  }).join('');
}

async function checkAgenda(showMessage = false) {
  const version = ++state.agendaVersion;
  if (!state.ids.length) { renderAgenda([]); $('conflicts').innerHTML = ''; return; }
  $('agenda-status').textContent = 'Checking your day…';
  try {
    const data = await post('/api/agenda', {talk_ids:state.ids});
    if (version !== state.agendaVersion) return;
    remember(data.talks);
    renderAgenda(data.talks.map((talk) => state.talks.get(talk.id)), data.clashes);
    renderConflicts(data);
    if (data.source === 'fallback') setSource(data);
    if (showMessage && !data.clashes.length) notify('Your agenda has no time clashes. You’re good to go.');
  } catch (error) {
    if (version !== state.agendaVersion) return;
    renderAgenda(state.ids.map((id) => state.talks.get(id)).filter(Boolean));
    $('agenda-status').textContent = 'Clash check unavailable · Saved choices retained';
    $('conflicts').innerHTML = '';
    notify(error.message, true);
  }
}

function changeAgenda(ids) {
  $('notice').hidden = true;
  state.ids = [...new Set(ids)];
  persist();
  updateCardButtons();
  checkAgenda();
}

$('search-form').addEventListener('submit', (event) => { event.preventDefault(); search(); });
['track','level','captioned','search-mode'].forEach((id) => $(id).addEventListener('change', search));
$('reset-filters').addEventListener('click', () => { $('track').value = ''; $('level').value = ''; $('captioned').checked = false; $('query').value = ''; search(); });
async function explainMatch(button) {
  const panel = button.closest('.match-tools').querySelector('.match-explanation');
  const query = state.query.trim();
  panel.hidden = false;
  button.setAttribute('aria-expanded', 'true');
  if (!query) {
    panel.textContent = 'Search for an interest or describe a problem first, then ask why a talk fits.';
    return;
  }
  if (button.disabled) return;
  button.disabled = true;
  button.textContent = 'Finding supporting evidence…';
  panel.textContent = 'Checking this session’s content for supporting evidence.';
  panel.className = 'match-explanation';
  try {
    const data = await post('/api/explain', {talk_id:button.dataset.explain, query});
    const evidence = Array.isArray(data.evidence) ? data.evidence.filter((item) => item && typeof item.quote === 'string') : [];
    if (data.available === false || (!data.explanation && !evidence.length)) {
      panel.textContent = data.unavailable_reason || data.degraded_reason || data.detail || 'Supporting evidence unavailable. You can still read the session description and use search.';
      panel.className = 'match-explanation unavailable';
      return;
    }
    const label = data.source === 'elasticsearch' ? 'Session evidence · Elasticsearch' : data.source === 'ollama' ? `AI-generated · ${data.model || 'local model'}` : 'Session explanation';
    panel.innerHTML = `<p class="explanation-label">${escapeHTML(label)}</p>${data.explanation ? `<p>${escapeHTML(data.explanation)}</p>` : ''}${evidence.map((item) => `<blockquote><span>Session evidence · ${escapeHTML(item.field)}</span>${escapeHTML(item.quote)}</blockquote>`).join('')}`;
  } catch (error) {
    panel.textContent = `Supporting evidence unavailable: ${error.message}`;
    panel.className = 'match-explanation unavailable';
  } finally {
    button.disabled = false;
    button.innerHTML = 'Why this match? <span aria-hidden="true">✧</span>';
  }
}

$('talks').addEventListener('click', (event) => {
  const explain = event.target.closest('[data-explain]');
  if (explain) { explainMatch(explain); return; }
  const button = event.target.closest('[data-add]');
  if (!button) return;
  const id = button.dataset.add;
  changeAgenda(state.ids.includes(id) ? state.ids.filter((saved) => saved !== id) : [...state.ids, id]);
});
$('agenda-talks').addEventListener('click', (event) => {
  const button = event.target.closest('[data-remove]');
  if (button) changeAgenda(state.ids.filter((id) => id !== button.dataset.remove));
});
$('conflicts').addEventListener('click', (event) => {
  const button = event.target.closest('[data-replace]');
  if (button) changeAgenda(state.ids.map((id) => id === button.dataset.replace ? button.dataset.with : id));
});
$('clear-agenda').addEventListener('click', () => { changeAgenda([]); notify('Agenda cleared. Make room for something new.'); });
$('check-agenda').addEventListener('click', () => checkAgenda(true));
$('day-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const interests = $('interests').value.trim();
  if (!interests) { notify('Add an interest or two so we can find your talks.', true); $('interests').focus(); return; }
  const button = $('build-button');
  button.disabled = true;
  button.textContent = 'Finding your day…';
  try {
    const data = await post('/api/build-my-day', {interests, day:$('conference-day').value, ...filters()});
    remember(data.talks);
    changeAgenda(data.talks.map((talk) => talk.id));
    setSource(data);
    const dayLabel = data.day ? new Intl.DateTimeFormat('en-US', {month:'short',day:'numeric',timeZone:'UTC'}).format(new Date(`${data.day}T12:00:00Z`)) : 'day';
    notify(data.talks.length ? `Your ${dayLabel} is ready: ${data.talks.length} relevant talks${data.max_talks !== null && data.max_talks !== undefined ? ` (maximum ${data.max_talks})` : ''}, without the clashes. You can still make it yours.` : 'No talks match those interests and filters on this date. Try another day or a broader topic.');
    $('agenda').scrollIntoView({block:'nearest', behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
  } catch (error) { notify(error.message, true); }
  finally { button.disabled = false; button.innerHTML = 'Build my day <span aria-hidden="true">↗</span>'; }
});

['AI Inference + Agentic','Application Development + Delivery','Cloud Native Experience','Cloud Native Novice','Connectivity','Data Processing + Storage','Emerging + Advanced','Observability','Operations + Performance','Platform Engineering','Security','Maintainer Track','Inclusion + Accessibility','Kubernetes','Platform','Data'].forEach((track) => {
  const option = document.createElement('option'); option.value = track; option.textContent = track; $('track').appendChild(option);
});
document.querySelectorAll('[data-query]').forEach((button) => button.addEventListener('click', () => {
  $('query').value = button.dataset.query;
  $('search-mode').value = 'hybrid';
  search();
  $('discover').scrollIntoView({block:'start', behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
}));
document.querySelectorAll('[data-place-category]').forEach((button) => button.addEventListener('click', () => loadPlaces(button.dataset.placeCategory)));
renderAgenda([]);
search();
loadPlaces('stay');
if (state.ids.length) checkAgenda();
