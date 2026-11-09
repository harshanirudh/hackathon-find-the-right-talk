'use strict';

const $ = (id) => document.getElementById(id);
const escapeHTML = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state = {ids: [], talks: new Map(), searchController: null, agendaVersion: 0, agendaRevision: 0, query: '', searchResults: [], searchTotal: 0, origin: 'new', view: 'browse', planDay: null};
function talkDay(talk) {
  const parts = new Intl.DateTimeFormat('en-US', {timeZone:'America/Denver', year:'numeric', month:'2-digit', day:'2-digit'}).formatToParts(new Date(talk.start));
  const get = (type) => parts.find((part) => part.type === type).value;
  return `${get('year')}-${get('month')}-${get('day')}`;
}
function syncPlanDay(day) {
  state.planDay = day;
  if (day && [...$('conference-day').options].some((option) => option.value === day)) $('conference-day').value = day;
}
try {
  const stored = JSON.parse(localStorage.getItem('righttalk-agenda') || '[]');
  if (Array.isArray(stored)) state.ids = [...new Set(stored.filter((id) => typeof id === 'string'))].slice(0, 100);
} catch (_) { /* Private browsing or a stale value should not break planning. */ }
if (state.ids.length) state.origin = 'restored';

function notify(message, error = false) {
  $('notice-text').textContent = message;
  $('notice').className = `notice${error ? ' error' : ''}`;
  $('notice').hidden = false;
}
$('dismiss-notice').addEventListener('click', () => { $('notice').hidden = true; });

let tooltipOwner = null;
let tooltipPinned = false;
function hideTooltip() {
  tooltipOwner?.removeAttribute('aria-describedby');
  tooltipOwner = null;
  tooltipPinned = false;
  $('feature-tooltip').hidden = true;
}
function showTooltip(button) {
  hideTooltip();
  tooltipOwner = button;
  const tooltip = $('feature-tooltip');
  tooltip.textContent = button.dataset.tooltip;
  tooltip.hidden = false;
  button.setAttribute('aria-describedby', tooltip.id);
  const rect = button.getBoundingClientRect();
  const box = tooltip.getBoundingClientRect();
  tooltip.style.left = `${Math.max(16, Math.min(rect.left, innerWidth - box.width - 16))}px`;
  tooltip.style.top = `${rect.bottom + box.height + 16 < innerHeight ? rect.bottom + 8 : Math.max(16, rect.top - box.height - 8)}px`;
}
document.querySelectorAll('[data-tooltip]').forEach((button) => {
  button.addEventListener('mouseenter', () => showTooltip(button));
  button.addEventListener('mouseleave', () => { if (!tooltipPinned && document.activeElement !== button) hideTooltip(); });
  button.addEventListener('focus', () => showTooltip(button));
  button.addEventListener('blur', hideTooltip);
  button.addEventListener('click', () => { if (tooltipOwner === button && tooltipPinned) hideTooltip(); else { showTooltip(button); tooltipPinned = true; } });
});
document.addEventListener('keydown', (event) => { if (event.key === 'Escape') hideTooltip(); });
document.addEventListener('pointerdown', (event) => { if (!event.target.closest('[data-tooltip]')) hideTooltip(); });
window.addEventListener('scroll', hideTooltip, true);

function persist() {
  try { localStorage.setItem('righttalk-agenda', JSON.stringify(state.ids)); }
  catch (_) { notify('Your agenda is available for this visit. This browser could not save it for next time.'); }
}

function remember(talks) {
  talks.forEach((talk) => state.talks.set(talk.id, {...state.talks.get(talk.id), ...talk}));
}

function filters() {
  return {track: $('track').value || undefined, level: $('level').value || undefined, captioned_only: $('captioned').checked, mode: 'auto'};
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
  $('search-mode-note').textContent = data.degraded_reason || data.strategy_reason || '';
  $('search-mode-note').hidden = !data.degraded_reason && !data.strategy_reason;
  $('search-mode-note').classList.toggle('warning', Boolean(data.degraded_reason));
}

const experienceLabel = (level) => Array.isArray(level) ? level.join(' + ') : level || '';

function showInterpretation(data, id) {
  const node = $(id), intent = data.interpretation;
  node.hidden = !intent;
  if (!intent) return;
  const details = [intent.query ? `Topic: ${intent.query}` : 'All topics', intent.level ? `level: ${experienceLabel(intent.level)}` : '',
    intent.max_talks !== null ? `maximum ${intent.max_talks} talks` : '',
    intent.captioned_only ? 'captioned only' : '', intent.day || ''].filter(Boolean).join(' · ');
  node.textContent = `${intent.source === 'openai' ? 'Interpreted by OpenAI' : 'Basic interpretation'} · ${details}${intent.degraded_reason ? ` · ${intent.degraded_reason}` : ''} · Retrieval: ${data.source === 'elasticsearch' ? 'Elasticsearch' : 'fallback'}`;
  node.classList.toggle('warning', Boolean(intent.degraded_reason));
}

function setPlannerSource(data) {
  const node = $('day-source');
  node.hidden = false;
  const fallback = data.source !== 'elasticsearch';
  node.className = `source-pill planner-source${fallback ? ' warning' : ''}`;
  node.textContent = `Day builder · ${fallback ? 'Fallback · Elasticsearch unavailable' : 'Elasticsearch'} · ${data.total} talks · ${data.mode === 'hybrid' ? 'Hybrid' : 'Keyword'}${data.degraded_reason ? ` · ${data.degraded_reason}` : ''}`;
}

function showDaySuggestions(data) {
  state.searchController?.abort();
  state.searchController = new AbortController();
  state.query = data.interests || '';
  $('query').value = state.query;
  state.view = 'day';
  const dateLabel = data.day ? new Intl.DateTimeFormat('en-US', {month:'short',day:'numeric',timeZone:'UTC'}).format(new Date(`${data.day}T12:00:00Z`)) : 'your plan';
  $('discover-title').textContent = data.talks.length ? `Suggested talks · ${dateLabel}` : `No matching sessions · ${dateLabel}`;
  $('discovery-context').textContent = data.talks.length ? 'These are the talks for this day. Review the details, remove any from your agenda, then save your plan alongside it.' : `No sessions matched this request${data.effective_level ? ` at ${experienceLabel(data.effective_level)} level` : ''}. Try another date or broader preferences.`;
  $('browse-controls').hidden = true;
  document.querySelector('.example-label').hidden = true;
  document.querySelector('.example-queries').hidden = true;
  $('browse-program').hidden = false;
  $('search-interpretation').hidden = true;
  renderSearchResults(data.talks, true, data.talks.length);
  if (!data.talks.length) $('talks').innerHTML = `<div class="empty-results">No matching sessions for ${escapeHTML(dateLabel)}.<br>Try another date or broaden your preferences.</div>`;
  setSource({...data, total:data.talks.length});
  $('talks').setAttribute('aria-busy', 'false');
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

let plannerKey = '';
let editingPlan = null;
try { plannerKey = localStorage.getItem('righttalk-planner-key') || ''; } catch (_) { /* Session-only key. */ }
if (!/^[a-f0-9]{64}$/.test(plannerKey)) {
  plannerKey = Array.from(crypto.getRandomValues(new Uint8Array(32)), (b) => b.toString(16).padStart(2, '0')).join('');
  try { localStorage.setItem('righttalk-planner-key', plannerKey); }
  catch (_) { notify('Keep a copy of your private plan key; this browser cannot retain it.'); }
}
$('planner-key').value = plannerKey;

function planApi(path = '', method = 'GET', body) {
  return api(`/api/plans${path}`, {method, headers:{'Content-Type':'application/json', 'X-Planner-Key':plannerKey},
    ...(body === undefined ? {} : {body:JSON.stringify(body)})});
}

function selectTab(panelId) {
  document.querySelectorAll('[data-tab]').forEach((tab) => {
    const selected = tab.dataset.tab === panelId;
    tab.setAttribute('aria-selected', String(selected));
    tab.tabIndex = selected ? 0 : -1;
    $(tab.dataset.tab).hidden = !selected;
  });
}
$('saved-library').addEventListener('toggle', () => { if ($('saved-library').open) loadPlans(); });
document.querySelector('.agenda-link').addEventListener('click', () => selectTab('day-panel'));
document.querySelectorAll('[data-tab]').forEach((tab, index, tabs) => {
  tab.addEventListener('click', () => selectTab(tab.dataset.tab));
  tab.addEventListener('keydown', (event) => {
    const step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
    if (!step && !['Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const next = tabs[event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + step + tabs.length) % tabs.length];
    next.click(); next.focus();
  });
  tab.tabIndex = index === 0 ? 0 : -1;
});

async function loadPlans() {
  $('saved-plans-list').setAttribute('aria-busy', 'true');
  try {
    const data = await planApi();
    $('plans-source').textContent = 'Elasticsearch storage';
    $('plans-source').className = 'source-pill';
    $('saved-plans-list').innerHTML = data.plans.length ? data.plans.map((plan) =>
      `<article class="saved-plan"><h3>${escapeHTML(plan.name)}</h3><p>${plan.talk_count} talks${plan.day ? ` · ${escapeHTML(plan.day)}` : ''}</p><div><button type="button" data-load-plan="${escapeHTML(plan.id)}">Load & edit</button><button type="button" class="text-button" data-delete-plan="${escapeHTML(plan.id)}">Delete</button></div></article>`).join('') : '<p class="venue-empty">No saved plans yet. Build a day, then save it here.</p>';
  } catch (error) {
    $('plans-source').textContent = 'Saved plans unavailable';
    $('plans-source').className = 'source-pill warning';
    $('saved-plans-list').textContent = error.message;
  } finally { $('saved-plans-list').setAttribute('aria-busy', 'false'); }
}

function setEditingPlan(plan = null) {
  editingPlan = plan;
  $('update-plan-button').hidden = !plan;
  $('plan-edit-note').hidden = !plan;
  $('plan-name').value = plan ? plan.name : '';
  $('save-plan-button').textContent = plan ? 'Save changes' : 'Save plan';
  $('plan-edit-note').textContent = plan ? `Editing “${plan.name}”. Save changes here, or save a new copy.` : '';
  renderSaveState();
}

function renderSaveState() {
  const changed = editingPlan && (JSON.stringify(state.ids) !== JSON.stringify(editingPlan.talk_ids) || $('plan-name').value.trim() !== editingPlan.name);
  $('plan-save-status').textContent = editingPlan ? changed ? 'Unsaved changes to this plan.' : `Saved as “${editingPlan.name}”.` : 'Not saved as a plan yet.';
}
$('plan-name').addEventListener('input', renderSaveState);

async function saveCurrentPlan(update = false) {
  if (!state.ids.length) { notify('Add talks to your day before saving a plan.', true); return; }
  if (!$('plan-name').reportValidity()) return;
  const ids = [...state.ids];
  const revision = state.agendaRevision;
  const selectedDays = new Set(ids.map((id) => state.talks.has(id) ? talkDay(state.talks.get(id)) : null));
  const day = selectedDays.size === 1 ? [...selectedDays][0] : null;
  $('save-plan-button').disabled = $('update-plan-button').disabled = true;
  try {
    const data = await planApi(update ? `/${encodeURIComponent(editingPlan.id)}` : '', update ? 'PUT' : 'POST',
      {name:$('plan-name').value.trim(), talk_ids:ids, day:day || null});
    if (revision === state.agendaRevision) setEditingPlan(data);
    await loadPlans();
    notify(revision !== state.agendaRevision ? 'The earlier version was saved. Your newer agenda changes are still unsaved.' : update ? 'Saved plan updated in Elasticsearch.' : 'Your plan is saved in Elasticsearch.');
  } catch (error) { notify(error.message, true); }
  finally { $('save-plan-button').disabled = $('update-plan-button').disabled = !state.ids.length; }
}
$('save-plan-form').addEventListener('submit', (event) => { event.preventDefault(); saveCurrentPlan(Boolean(editingPlan)); });
$('update-plan-button').addEventListener('click', () => saveCurrentPlan(false));
$('refresh-plans').addEventListener('click', loadPlans);
$('saved-plans-list').addEventListener('click', async (event) => {
  const load = event.target.closest('[data-load-plan]');
  const remove = event.target.closest('[data-delete-plan]');
  if (!load && !remove) return;
  const button = load || remove;
  const revision = load ? ++state.agendaRevision : state.agendaRevision;
  button.disabled = true;
  if (load) {
    $('plan-name').disabled = true;
    $('save-plan-button').disabled = $('update-plan-button').disabled = true;
  }
  try {
    if (remove) {
      if (!window.confirm('Delete this saved plan? This cannot be undone.')) return;
      await planApi(`/${encodeURIComponent(remove.dataset.deletePlan)}`, 'DELETE');
      if (editingPlan?.id === remove.dataset.deletePlan) setEditingPlan();
      await loadPlans(); notify('Saved plan deleted.');
    } else {
      const data = await planApi(`/${encodeURIComponent(load.dataset.loadPlan)}`);
      if (revision !== state.agendaRevision) { notify('Your agenda changed while the plan was loading. Your current choices were kept.'); return; }
      remember(data.talks);
      const available = new Set(data.talks.map((talk) => talk.id));
      state.origin = 'saved';
      changeAgenda(data.talk_ids.filter((id) => available.has(id)));
      if (data.day && [...$('conference-day').options].some((option) => option.value === data.day)) $('conference-day').value = data.day;
      setEditingPlan(data); selectTab('day-panel');
      $('saved-library').open = false;
      showDaySuggestions({...data, total:data.talks.length, mode:'keyword'});
      $('discover-title').textContent = `Talks in “${data.name}”`;
      $('interests').value = '';
      $('day-interpretation').hidden = $('day-selection-note').hidden = true;
      $('day-source').hidden = false;
      $('day-source').className = 'source-pill planner-source';
      $('day-source').textContent = `Saved plan · Elasticsearch · ${data.talks.length} talks`;
      $('plan-name').focus();
      notify(available.size < data.talk_ids.length ? 'Plan loaded. Some talks are no longer in the catalogue.' : 'Plan loaded. Edit your day and choose Save changes beside the agenda.');
    }
  } catch (error) { notify(error.message, true); }
  finally {
    button.disabled = false;
    if (load) {
      $('plan-name').disabled = false;
      $('save-plan-button').disabled = $('update-plan-button').disabled = !state.ids.length;
    }
  }
});
$('copy-plan-key').addEventListener('click', async () => {
  try { await navigator.clipboard.writeText(plannerKey); notify('Private plan key copied. Keep it private.'); }
  catch (_) { $('planner-key').select(); notify('Select and copy your private key from the field.'); }
});
$('use-plan-key-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const key = $('import-planner-key').value.trim();
  if (!/^[a-f0-9]{64}$/.test(key)) { notify('Enter a complete 64-character private plan key.', true); return; }
  plannerKey = key; $('planner-key').value = key;
  try { localStorage.setItem('righttalk-planner-key', key); }
  catch (_) { notify('This key will only be available for this visit.'); }
  $('import-planner-key').value = ''; setEditingPlan(); loadPlans();
});
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
  const captioned = (facets.captioned || []).find((item) => item.key === true || item.key === 1 || item.key === 'true');
  $('captioned-count').textContent = `Captioned only (${captioned?.doc_count || 0})`;
}
async function loadMore(button) {
  const searchController = state.searchController;
  button.disabled = true; button.textContent = 'Loading more talks…';
  const params = new URLSearchParams({q:state.query, limit:'24', offset:String(state.searchResults.length)});
  params.set('smart', String($('smart-search').checked));
  Object.entries(filters()).forEach(([key,value]) => { if (value !== undefined) params.set(key,value); });
  try {
    const data = await api(`/api/search?${params}`);
    if (searchController !== state.searchController) return;
    remember(data.talks); renderSearchResults(data.talks, false, data.total); updateFacets(data.facets); setSource(data);
  } catch (error) { if (searchController !== state.searchController) return; button.disabled = false; button.textContent = 'More talks failed to load · retry'; notify(error.message, true); }
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
const range = (talk) => `${new Intl.DateTimeFormat('en-US', {month:'short', day:'numeric', timeZone:'America/Denver'}).format(new Date(talk.start))} · ${time(talk.start)} – ${time(talk.end)}`;

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
  params.set('smart', String($('smart-search').checked));
  Object.entries(filters()).forEach(([key, value]) => { if (value !== undefined) params.set(key, value); });
  try {
    const data = await api(`/api/search?${params}`, {signal:controller.signal});
    if (controller !== state.searchController) return;
    remember(data.talks);
    state.query = params.get('q');
    state.view = 'browse';
    $('discover-title').textContent = 'Explore the programme';
    $('discovery-context').textContent = 'Browsing the programme. Add any talk to your agenda; your current day stays alongside it.';
    $('browse-controls').hidden = false;
    document.querySelector('.example-label').hidden = false;
    document.querySelector('.example-queries').hidden = false;
    $('browse-program').hidden = true;
    renderSearchResults(data.talks, true, data.total);
    updateFacets(data.facets);
    setSource(data);
    showInterpretation(data, 'search-interpretation');
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
  const dates = [...new Set(talks.map((talk) => talk.start.slice(0, 10)))].sort();
  document.querySelector('.date-line').textContent = dates.length ? dates.map((day) =>
    new Intl.DateTimeFormat('en-US', {month:'short', day:'numeric', timeZone:'UTC'}).format(new Date(`${day}T12:00:00Z`))).join(' · ') + ' · MST' : 'Choose talks for Nov 10–12 · MST';
  $('agenda-count').textContent = String(talks.length);
  $('clear-agenda').disabled = state.ids.length === 0;
  $('check-agenda').disabled = talks.length === 0;
  $('save-plan-button').disabled = talks.length === 0;
  $('update-plan-button').disabled = talks.length === 0;
  document.querySelector('.agenda-save').hidden = !state.ids.length;
  $('draft-origin').hidden = state.origin !== 'restored' || !state.ids.length;
  $('draft-origin').textContent = 'Restored your previous browser draft. Clear it to start fresh.';
  $('agenda-status').textContent = talks.length === 0 ? 'Your day is a blank canvas.' : clashes.length ? `${clashes.length} clash${clashes.length === 1 ? '' : 'es'} to resolve · ${talks.length} talks saved in this browser` : `${talks.length} talk${talks.length === 1 ? '' : 's'} saved in this browser · No clashes. All yours.`;
  $('agenda-talks').innerHTML = talks.length ? talks.map((talk) => `<article class="agenda-item"><div class="agenda-time"><span>${escapeHTML(range(talk))}</span><button class="remove-button" type="button" data-remove="${escapeHTML(talk.id)}" aria-label="Remove ${escapeHTML(talk.title)}">×</button></div><h3>${escapeHTML(talk.title)}</h3>${talk.reason ? `<p class="reason">Why: ${escapeHTML(talk.reason)}</p>` : ''}<p class="room">${escapeHTML(talk.room)} · ${escapeHTML(talk.track)}</p></article>`).join('') : '<div class="empty-agenda"><span class="empty-symbol" aria-hidden="true">↗</span>Add a talk that catches your eye,<br>or let your interests build the day.</div>';
  updateCardButtons();
  renderSaveState();
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
    const data = await post('/api/agenda', {talk_ids:state.ids, day:state.planDay});
    if (version !== state.agendaVersion) return;
    remember(data.talks);
    const dates = new Set(data.talks.map(talkDay));
    if (dates.size !== 1) throw new Error('This browser draft contains sessions from multiple days. Choose Clear to start a separate day plan.');
    syncPlanDay(data.day || [...dates][0]);
    renderAgenda(data.talks.map((talk) => state.talks.get(talk.id)), data.clashes);
    renderConflicts(data);
    if (data.source === 'fallback') $('agenda-status').textContent += ' · Fallback data; Elasticsearch unavailable';
    if (showMessage) {
      notify(data.clashes.length
        ? `Found ${data.clashes.length} time clash${data.clashes.length === 1 ? '' : 'es'} in your saved agenda. Choose a suggested swap or remove a talk to resolve them.`
        : `No time clashes found. Your ${data.talks.length} selected talks are saved in this browser.`);
    }
  } catch (error) {
    if (version !== state.agendaVersion) return;
    renderAgenda(state.ids.map((id) => state.talks.get(id)).filter(Boolean));
    $('agenda-status').textContent = 'Clash check unavailable · Saved choices retained';
    $('conflicts').innerHTML = '';
    notify(error.message, true);
  }
}

function changeAgenda(ids) {
  const dates = new Set(ids.map((id) => state.talks.has(id) ? talkDay(state.talks.get(id)) : null).filter(Boolean));
  if (dates.size > 1) {
    notify(`This plan is for ${state.planDay || [...dates][0]}. Choose Clear to start a new day before adding sessions from another date.`, true);
    return false;
  }
  state.agendaRevision += 1;
  $('retained-draft-note').hidden = true;
  $('notice').hidden = true;
  state.ids = [...new Set(ids)];
  syncPlanDay(state.ids.length ? [...dates][0] || state.planDay : null);
  persist();
  updateCardButtons();
  renderSaveState();
  checkAgenda();
}

$('search-form').addEventListener('submit', (event) => { event.preventDefault(); search(); });
$('browse-program').addEventListener('click', () => {
  $('query').value = ''; $('track').value = ''; $('level').value = ''; $('captioned').checked = false;
  $('smart-search').checked = false;
  $('browse-controls').hidden = false; search();
});
['track','level','captioned'].forEach((id) => $(id).addEventListener('change', search));
$('smart-search').addEventListener('change', search);
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
$('clear-agenda').addEventListener('click', () => {
  state.origin = 'new'; setEditingPlan(); changeAgenda([]);
  ['day-source', 'day-interpretation', 'day-selection-note'].forEach((id) => { $(id).hidden = true; });
  if (state.view === 'day') $('discovery-context').textContent = 'Your agenda is empty. Add a suggestion again, browse other talks, or build a new day.';
  notify('Agenda cleared. Make room for something new.');
});
$('check-agenda').addEventListener('click', () => checkAgenda(true));
$('day-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const interests = $('interests').value.trim();
  if (!interests) { notify('Add an interest or two so we can find your talks.', true); $('interests').focus(); return; }
  const button = $('build-button');
  button.disabled = true;
  button.textContent = 'Finding your day…';
  const revision = state.agendaRevision;
  const requestedDay = $('conference-day').value;
  try {
    const data = await post('/api/build-my-day', {interests, smart:$('smart-day').checked, day:requestedDay,
      captioned_only:$('day-captioned').checked, mode:'auto'});
    if (revision !== state.agendaRevision || $('conference-day').value !== requestedDay || $('interests').value.trim() !== interests) {
      notify('Your day or request changed while planning. Your current choices were kept. Build again when ready.');
      return;
    }
    setPlannerSource(data);
    showInterpretation(data, 'day-interpretation');
    $('day-selection-note').textContent = data.selection_note || '';
    $('day-selection-note').hidden = !data.selection_note;
    showDaySuggestions(data);
    if (!data.talks.length) {
      const retainedDate = state.planDay ? new Intl.DateTimeFormat('en-US', {month:'short',day:'numeric',timeZone:'UTC'}).format(new Date(`${state.planDay}T12:00:00Z`)) : 'earlier';
      const requestDate = new Intl.DateTimeFormat('en-US', {month:'short',day:'numeric',timeZone:'UTC'}).format(new Date(`${data.day}T12:00:00Z`));
      $('retained-draft-note').hidden = !state.ids.length;
      $('retained-draft-note').textContent = `Existing ${retainedDate} draft kept. Your latest ${requestDate} request found no matches; saving here saves the ${retainedDate} draft.`;
      notify(`No talks match those interests and filters${data.effective_level ? ` at ${experienceLabel(data.effective_level)} level` : ''} on this date. Your current agenda is unchanged. Try another day or a broader topic.`);
      return;
    }
    remember(data.talks);
    state.origin = 'built';
    setEditingPlan();
    changeAgenda(data.talks.map((talk) => talk.id));
    const dayLabel = data.day ? new Intl.DateTimeFormat('en-US', {month:'short',day:'numeric',timeZone:'UTC'}).format(new Date(`${data.day}T12:00:00Z`)) : 'day';
    notify(`Your ${dayLabel} is ready: ${data.talks.length} relevant talks${data.max_talks !== null && data.max_talks !== undefined ? ` (maximum ${data.max_talks})` : ''}, without the clashes.${data.effective_level ? ` Experience: ${experienceLabel(data.effective_level)}.` : ''} You can still make it yours.`);
    $('agenda').scrollIntoView({block:'nearest', behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
  } catch (error) { notify(error.message, true); }
  finally { button.disabled = false; button.innerHTML = 'Build my day <span aria-hidden="true">↗</span>'; }
});

['AI Inference + Agentic','Application Development + Delivery','Cloud Native Experience','Cloud Native Novice','Connectivity','Data Processing + Storage','Emerging + Advanced','Observability','Operations + Performance','Platform Engineering','Security','Maintainer Track','Inclusion + Accessibility','Kubernetes','Platform','Data'].forEach((track) => {
  const option = document.createElement('option'); option.value = track; option.textContent = track; $('track').appendChild(option);
});
document.querySelectorAll('[data-query]').forEach((button) => button.addEventListener('click', () => {
  $('query').value = button.dataset.query;
  search();
  $('discover').scrollIntoView({block:'start', behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
}));
document.querySelectorAll('[data-place-category]').forEach((button) => button.addEventListener('click', () => loadPlaces(button.dataset.placeCategory)));
renderAgenda([]);
search();
loadPlaces('stay');
if (state.ids.length) { notify('Restored your previous agenda from this browser. Choose Clear to start fresh.'); checkAgenda(); }
