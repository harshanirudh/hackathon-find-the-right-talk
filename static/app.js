'use strict';

const $ = (id) => document.getElementById(id);
const escapeHTML = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state = {ids: [], talks: new Map(), searchController: null, agendaVersion: 0, agendaRevision: 0, draftEpoch: 0, saving: false, loadingPlan: false, query: '', searchResults: [], searchTotal: 0, origin: 'new', view: 'browse', planDay: null, conference: null, conferenceEpoch: 0};
function talkDay(talk) {
  const parts = new Intl.DateTimeFormat('en-US', {timeZone:'America/Denver', year:'numeric', month:'2-digit', day:'2-digit'}).formatToParts(new Date(talk.start));
  const get = (type) => parts.find((part) => part.type === type).value;
  return `${get('year')}-${get('month')}-${get('day')}`;
}
function syncPlanDay(day) {
  state.planDay = day;
  if (day && [...$('conference-day').options].some((option) => option.value === day)) $('conference-day').value = day;
}
function updateScope() {
  const multi = $('plan-scope').value === 'conference';
  $('planner-title').textContent = multi ? 'Plan your conference' : 'Plan your conference day';
  $('single-day-control').hidden = multi;
  $('smart-option').hidden = multi;
  $('scope-note').hidden = !multi;
  $('interests').maxLength = multi ? 2000 : 500;
  $('build-button').textContent = multi ? 'Build all 3 days ↗' : 'Build my day ↗';
}
$('plan-scope').addEventListener('change', updateScope);
$('interests').addEventListener('input', () => {
  const days = new Set([...$('interests').value.matchAll(/\bday\s*([123])\b/gi)].map((match) => match[1]));
  if (days.size > 1 && $('plan-scope').value !== 'conference') { $('plan-scope').value = 'conference'; updateScope(); }
});

function exitConference() {
  if (!state.conference) return;
  state.conference = null; state.conferenceEpoch += 1;
  $('conference-plans').hidden = true;
  $('return-single-draft').hidden = true;
  $('agenda-content').hidden = false;
  $('browse-program').hidden = false;
  $('agenda-title').firstChild.textContent = 'Your day ';
  $('plan-scope').value = 'day'; updateScope();
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
  return {track: $('track').value || undefined, level: $('level').value || undefined, captioned_only: $('captioned').checked, mode: 'auto', day:state.planDay || $('conference-day').value};
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
  if (id === 'day-interpretation') $('interpretation-details').hidden = !intent;
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
  state.view = 'day';
  $('programme-drawer').open = false;
  $('talks').innerHTML = '';
  state.searchResults = []; state.searchTotal = 0;
  $('talks').setAttribute('aria-busy', 'false');
  $('latest-empty').hidden = data.talks.length > 0;
  $('agenda-content').hidden = !data.talks.length;
  document.querySelector('.agenda-save').hidden = !data.talks.length;
  if (!data.talks.length) {
    const label = dayLabel(data.day);
    $('latest-result-title').textContent = `No matching sessions · ${label}`;
    $('latest-result-copy').textContent = `No sessions matched${data.effective_level ? ` ${experienceLabel(data.effective_level)} level` : ' these preferences'} on ${label}. Try another date or broaden the request.`;
    $('show-retained-draft').hidden = !state.ids.length;
    $('show-retained-draft').textContent = `View retained ${dayLabel(state.planDay)} draft`;
  }
}

function dayLabel(day) {
  return day ? new Intl.DateTimeFormat('en-US', {month:'short',day:'numeric',timeZone:'UTC'}).format(new Date(`${day}T12:00:00Z`)) : 'earlier';
}

function openProgramme() {
  $('programme-drawer').open = true;
  search();
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
  if (panelId === 'venue-panel' && !state.placesLoaded) loadPlaces(state.placeCategory || 'stay');
}
$('saved-library').addEventListener('toggle', () => { if ($('saved-library').open) loadPlans(); });

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
  if (state.saving || state.loadingPlan) return;
  if (!state.ids.length) { notify('Add talks to your day before saving a plan.', true); return; }
  if (!$('plan-name').reportValidity()) return;
  const ids = [...state.ids];
  const revision = state.agendaRevision;
  const epoch = state.draftEpoch;
  const submittedName = $('plan-name').value.trim();
  const selectedDays = new Set(ids.map((id) => state.talks.has(id) ? talkDay(state.talks.get(id)) : null));
  const day = selectedDays.size === 1 ? [...selectedDays][0] : null;
  $('save-plan-button').disabled = $('update-plan-button').disabled = true;
  state.saving = true;
  try {
    const data = await planApi(update ? `/${encodeURIComponent(editingPlan.id)}` : '', update ? 'PUT' : 'POST',
      {name:submittedName, talk_ids:ids, day:day || null});
    const sameDraft = epoch === state.draftEpoch;
    const changed = revision !== state.agendaRevision || $('plan-name').value.trim() !== submittedName;
    if (sameDraft) {
      const currentName = $('plan-name').value;
      setEditingPlan(data);
      if (changed) { $('plan-name').value = currentName; renderSaveState(); }
    }
    await loadPlans();
    const latestChanged = revision !== state.agendaRevision || $('plan-name').value.trim() !== submittedName;
    notify(epoch !== state.draftEpoch ? 'The earlier draft was saved separately. Your current draft was kept.' : latestChanged ? 'Plan saved. Your newer edits are not saved yet.' : update ? 'Saved plan updated in Elasticsearch.' : 'Your plan is saved in Elasticsearch.');
  } catch (error) { notify(error.message, true); }
  finally { state.saving = false; $('save-plan-button').disabled = $('update-plan-button').disabled = !state.ids.length || state.loadingPlan; }
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
    state.draftEpoch += 1;
    state.loadingPlan = true;
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
      const conferenceDay = state.conference?.days.find((day) => day.day === data.day);
      if (conferenceDay) {
        conferenceDay.epoch += 1; conferenceDay.revision += 1;
        Object.assign(conferenceDay, {talks:data.talks, ids:data.talk_ids.filter((id) => data.talks.some((talk) => talk.id === id)), name:data.name, plan:data, source:'elasticsearch', mode:'none', status:'ok', interests:'', effective_level:null, max_talks:null, selection_note:'', degraded_reason:null, openedSaved:true});
        remember(data.talks); renderConferenceDay(conferenceDay);
        $('saved-library').open = false;
        $(`daily-name-${conferenceDay.day}`)?.focus();
        notify(`${dayLabel(conferenceDay.day)} opened. The other daily drafts are unchanged.`);
        return;
      }
      exitConference();
      remember(data.talks);
      const available = new Set(data.talks.map((talk) => talk.id));
      state.origin = 'saved';
      changeAgenda(data.talk_ids.filter((id) => available.has(id)));
      if (data.day && [...$('conference-day').options].some((option) => option.value === data.day)) $('conference-day').value = data.day;
      setEditingPlan(data); selectTab('day-panel');
      $('saved-library').open = false;
      $('request-editor').open = false;
      showDaySuggestions({...data, total:data.talks.length, mode:'keyword'});
      $('interests').value = '';
      $('day-interpretation').hidden = $('day-selection-note').hidden = true;
      $('day-source').hidden = false;
      $('day-source').className = 'source-pill planner-source';
      $('day-source').textContent = `Saved plan · Elasticsearch · ${data.talks.length} sessions`;
      $('plan-name').focus();
      notify(available.size < data.talk_ids.length ? 'Plan loaded. Some talks are no longer in the catalogue.' : 'Plan loaded. Edit your day and choose Save changes beside the agenda.');
    }
  } catch (error) { notify(error.message, true); }
  finally {
    button.disabled = false;
    if (load) {
      state.loadingPlan = false;
      $('plan-name').disabled = false;
      $('save-plan-button').disabled = $('update-plan-button').disabled = !state.ids.length || state.saving;
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
  state.draftEpoch += 1;
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
  state.placeCategory = category;
  state.placesLoaded = true;
  const version = (state.placeVersion || 0) + 1;
  state.placeVersion = version;
  const radius = Number($('walking-budget').value) * 80;
  $('venue-places').setAttribute('aria-busy', 'true');
  $('venue-places').innerHTML = '<p class="venue-empty">Finding places within your walking budget…</p>';
  document.querySelectorAll('[data-place-category]').forEach((chip) => {
    chip.classList.toggle('active', chip.dataset.placeCategory === category);
    chip.setAttribute('aria-pressed', String(chip.dataset.placeCategory === category));
  });
  try {
    const data = await api(`/api/places?category=${encodeURIComponent(category)}&radius_m=${radius}`);
    if (version !== state.placeVersion) return;
    $('venue-source').textContent = `Elasticsearch geo search · ${data.total} places within ${radius} m${data.data_note === 'curated OSM fallback' ? ' · curated OSM snapshot' : ''}`;
    $('venue-source').className = 'source-pill';
    $('venue-places').innerHTML = data.places.length ? data.places.map((place) => `<article class="place-card"><div class="place-title"><h3>${escapeHTML(place.name)}</h3><span class="place-category">${escapeHTML(place.category)}</span></div><p class="place-distance">${Math.round(place.distance_m)} m · about ${place.walking_minutes} min walk</p><p class="place-address">${escapeHTML(place.address || '')}</p><a href="https://www.openstreetmap.org/?mlat=${encodeURIComponent(place.lat)}&mlon=${encodeURIComponent(place.lon)}" target="_blank" rel="noreferrer">View in OpenStreetMap ↗</a></article>`).join('') : '<p class="venue-empty">No indexed places in this category within that budget. Try a wider radius.</p>';
  } catch (error) {
    if (version !== state.placeVersion) return;
    $('venue-source').textContent = 'Venue search unavailable';
    $('venue-source').className = 'source-pill warning';
    $('venue-places').textContent = error.message;
  } finally { if (version === state.placeVersion) $('venue-places').setAttribute('aria-busy', 'false'); }
}
$('walking-budget').addEventListener('change', () => loadPlaces(state.placeCategory || 'stay'));

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

function sessionDetails(talk, query = state.query) {
  return `<details class="session-details"><summary>Session details</summary><p class="talk-description">${escapeHTML(talk.description)}</p><div class="accessibility">${accessNotes(talk)}</div><p class="talk-origin ${talk.dataset ? 'official' : 'sample'}">${talk.dataset ? 'Official conference session' : 'Illustrative demo sample'}${talk.source_url ? ` · <a href="${escapeHTML(talk.source_url)}" target="_blank" rel="noreferrer">Official listing ↗</a>` : ''}</p><div class="match-tools"><button type="button" class="explain-button" data-explain="${escapeHTML(talk.id)}" data-evidence-query="${escapeHTML(query || '')}" aria-expanded="false">Why this match?</button><div class="match-explanation" role="status" hidden></div></div></details>`;
}

function conferenceCount() {
  return state.conference ? state.conference.days.reduce((count, day) => count + day.ids.length, 0) : 0;
}
function renderConferenceDay(day) {
  const source = day.source === 'elasticsearch' ? 'Elasticsearch' : day.source === 'fallback' ? 'Fallback · Elasticsearch unavailable' : day.source === 'not_queried' ? 'Not queried' : 'Retrieval unavailable';
  const mode = day.mode === 'hybrid' ? 'Hybrid' : day.mode === 'keyword' ? 'Keyword' : '';
  const changed = day.plan && (JSON.stringify(day.ids) !== JSON.stringify(day.plan.talk_ids) || day.name !== day.plan.name);
  const status = day.plan ? changed ? 'Unsaved changes to this day.' : 'Saved in Elasticsearch.' : 'Daily draft · save before refreshing.';
  const selected = day.talks.filter((talk) => day.ids.includes(talk.id));
  const rows = selected.map((talk) => `<article class="agenda-item"><div class="agenda-time">${escapeHTML(range(talk))}</div><div class="agenda-body"><h3>${escapeHTML(talk.title)}</h3><p class="session-meta">${escapeHTML(talk.speaker)} · ${escapeHTML(talk.level)} · ${escapeHTML(talk.room)}</p>${talk.reason ? `<p class="reason">Why: ${escapeHTML(talk.reason)}</p>` : ''}${sessionDetails(talk, day.interests)}</div><button type="button" class="remove-button" data-conference-remove="${escapeHTML(talk.id)}" data-day="${day.day}" aria-label="Remove ${escapeHTML(talk.title)} from ${dayLabel(day.day)}">×</button></article>`).join('');
  const empty = day.status === 'error' ? day.error || 'This day could not be built. The other days are still available.' : day.ids.length ? '' : day.talks.length ? 'All sessions were removed from this day.' : day.selection_note || 'No matching sessions for this day. Broaden these preferences or choose another level.';
  const node = $(`conference-${day.day}`);
  node.innerHTML = `<div class="conference-day-header"><div><h3>Day ${day.day_number} · ${dayLabel(day.day)} <span class="count">${day.ids.length}</span></h3><p class="daily-preferences">${day.openedSaved ? 'Saved daily plan · original request details are not stored.' : `${escapeHTML(day.interests || 'All topics')} · ${escapeHTML(experienceLabel(day.effective_level) || 'all levels')}${day.max_talks != null ? ` · maximum ${day.max_talks} sessions` : ''}`}</p></div><span class="source-pill daily-source${day.source === 'fallback' || day.status === 'error' ? ' warning' : ''}">${escapeHTML(source)}${mode ? ` · ${mode}` : ''}</span></div>${day.degraded_reason ? `<p class="inline-note warning">${escapeHTML(day.degraded_reason)}</p>` : ''}${day.ids.length ? `<form class="daily-save-form" data-day-save="${day.day}"><label class="sr-only" for="daily-name-${day.day}">Name for ${dayLabel(day.day)}</label><input id="daily-name-${day.day}" data-day-name="${day.day}" value="${escapeHTML(day.name)}" maxlength="80" required><button class="primary-button" type="submit" ${day.saving ? 'disabled' : ''}>${day.saving ? 'Saving…' : day.plan ? 'Save changes' : 'Save this day'}</button></form><p class="daily-save-status">${escapeHTML(status)}</p>` : ''}${empty ? `<p class="daily-empty${day.status === 'error' ? ' warning' : ''}">${escapeHTML(empty)}</p>` : ''}${day.selection_note && day.ids.length ? `<p class="selection-note">${escapeHTML(day.selection_note)}</p>` : ''}<div class="daily-talks">${rows}</div>`;
  $('agenda-count').textContent = String(conferenceCount());
}
function renderConference(data) {
  const total = data.days.reduce((count, day) => count + day.talks.length, 0);
  if (total) {
    state.draftEpoch += 1; setEditingPlan(); state.ids = []; state.planDay = null; persist();
  }
  state.agendaVersion += 1; state.agendaRevision += 1; state.conferenceEpoch += 1;
  state.conference = {epoch:state.conferenceEpoch, days:data.days.map((day) => ({...day, ids:day.talks.map((talk) => talk.id), revision:0, epoch:0, saving:false, plan:null, name:`${dayLabel(day.day)} · ${day.interests || 'Conference day'}`.slice(0,80)}))};
  remember(data.days.flatMap((day) => day.talks));
  $('programme-drawer').open = false; state.searchController?.abort();
  $('latest-empty').hidden = true; $('retained-draft-note').hidden = true; $('draft-origin').hidden = true;
  $('agenda-content').hidden = true; document.querySelector('.agenda-save').hidden = true;
  $('browse-program').hidden = true; $('clear-agenda').hidden = false; $('clear-agenda').disabled = false;
  $('agenda-title').firstChild.textContent = 'Your conference ';
  document.querySelector('.date-line').textContent = 'Three daily plans · Nov 10–12 · save each day separately';
  $('conference-plans').hidden = false;
  $('conference-plans').innerHTML = state.conference.days.map((day) => `<section id="conference-${day.day}" class="conference-day" data-conference-day="${day.day}" aria-label="Day ${day.day_number}, ${dayLabel(day.day)}"></section>`).join('');
  state.conference.days.forEach(renderConferenceDay);
  $('return-single-draft').hidden = total > 0 || !state.ids.length;
  $('return-single-draft').textContent = `Return to retained ${dayLabel(state.planDay)} draft`;
  $('day-source').hidden = false; $('day-source').className = 'source-pill';
  $('day-source').textContent = `${data.interpretation_source === 'openai' ? 'OpenAI' : 'Request interpretation'} · ${data.extraction_calls} interpretation · 3 daily results`;
  $('interpretation-details').hidden = true; $('day-selection-note').hidden = true;
  $('request-editor').open = false;
  notify('Three daily results are ready. Review and save the available days separately.');
}
$('return-single-draft').addEventListener('click', () => {
  exitConference(); renderAgenda(state.ids.map((id) => state.talks.get(id)).filter(Boolean));
  $('day-source').hidden = true;
});
$('conference-plans').addEventListener('input', (event) => {
  const input = event.target.closest('[data-day-name]');
  if (!input || !state.conference) return;
  const day = state.conference.days.find((item) => item.day === input.dataset.dayName);
  day.name = input.value; day.revision += 1; state.agendaRevision += 1;
  const status = input.closest('.conference-day').querySelector('.daily-save-status');
  if (status) status.textContent = day.plan ? 'Unsaved changes to this day.' : 'Daily draft · save before refreshing.';
});
$('conference-plans').addEventListener('click', (event) => {
  const explain = event.target.closest('[data-explain]');
  if (explain) { explainMatch(explain); return; }
  const remove = event.target.closest('[data-conference-remove]');
  if (!remove || !state.conference) return;
  const day = state.conference.days.find((item) => item.day === remove.dataset.day);
  day.ids = day.ids.filter((id) => id !== remove.dataset.conferenceRemove);
  day.revision += 1; state.agendaRevision += 1; renderConferenceDay(day);
});
$('conference-plans').addEventListener('submit', async (event) => {
  const form = event.target.closest('[data-day-save]');
  if (!form || !state.conference) return;
  event.preventDefault();
  const context = state.conference;
  const day = context.days.find((item) => item.day === form.dataset.daySave);
  if (day.saving || !day.ids.length || !form.reportValidity()) return;
  const name = day.name.trim(), ids = [...day.ids], epoch = day.epoch;
  if (!name) { notify('Give this day a name before saving.', true); return; }
  day.saving = true; renderConferenceDay(day);
  try {
    const saved = await planApi(day.plan ? `/${encodeURIComponent(day.plan.id)}` : '', day.plan ? 'PUT' : 'POST', {name, talk_ids:ids, day:day.day});
    if (state.conference === context && day.epoch === epoch) { day.plan = saved; renderConferenceDay(day); }
    await loadPlans();
    notify(`${dayLabel(day.day)} saved in Elasticsearch. Open it from your saved plans to edit it on its own.`);
  } catch (error) { notify(error.message, true); }
  finally { day.saving = false; if (state.conference === context) renderConferenceDay(day); }
});
function talkCard(talk) {
  const selected = state.ids.includes(talk.id);
  const highlightField = ['description', 'tags'].find((field) => talk.highlights?.[field]?.length);
  return `<article class="talk-card"><div><p class="talk-top">${escapeHTML(range(talk))}</p><h3>${esHighlight(talk, 'title', talk.title)}</h3><p class="session-meta">${escapeHTML(talk.speaker)} · ${escapeHTML(talk.track)} · ${escapeHTML(talk.level)}</p>${highlightField ? `<p class="search-highlight">${esHighlight(talk, highlightField, '')}</p>` : ''}${sessionDetails(talk)}</div><button type="button" class="add-button${selected ? ' selected' : ''}" data-add="${escapeHTML(talk.id)}" aria-label="${selected ? 'Remove' : 'Add'} ${escapeHTML(talk.title)} ${selected ? 'from' : 'to'} agenda">${selected ? '✓ Added' : '+ Add'}</button></article>`;
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
    $('discovery-context').textContent = !$('latest-empty').hidden && state.planDay
      ? `Adding to the retained ${dayLabel(state.planDay)} draft. The latest ${dayLabel($('conference-day').value)} request found no matches.`
      : `Showing ${dayLabel(state.planDay || $('conference-day').value)}. Added sessions stay in this day’s schedule above.`;
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
    new Intl.DateTimeFormat('en-US', {month:'short', day:'numeric', timeZone:'UTC'}).format(new Date(`${day}T12:00:00Z`))).join(' · ') + ' · MST' : `${dayLabel($('conference-day').value)} · MST`;
  $('agenda-count').textContent = String(talks.length);
  $('clear-agenda').disabled = state.ids.length === 0;
  $('clear-agenda').hidden = state.ids.length === 0;
  document.querySelector('.clash-actions').hidden = !talks.length;
  $('check-agenda').disabled = talks.length === 0;
  $('save-plan-button').disabled = talks.length === 0 || state.saving || state.loadingPlan;
  $('update-plan-button').disabled = talks.length === 0 || state.saving || state.loadingPlan;
  document.querySelector('.agenda-save').hidden = !state.ids.length || !$('latest-empty').hidden;
  if (talks.length && !$('plan-name').value) $('plan-name').value = `${dayLabel(state.planDay)} · Conference day`;
  $('draft-origin').hidden = state.origin !== 'restored' || !state.ids.length;
  $('draft-origin').textContent = 'Restored your previous browser draft. Clear it to start fresh.';
  $('agenda-status').textContent = talks.length === 0 ? 'Your day is empty. Build a schedule above, or add sessions yourself.' : clashes.length ? `${clashes.length} clash${clashes.length === 1 ? '' : 'es'} to resolve · ${talks.length} talks saved in this browser` : `${talks.length} talk${talks.length === 1 ? '' : 's'} saved in this browser · No clashes. All yours.`;
  $('agenda-talks').innerHTML = talks.length ? talks.map((talk) => `<article class="agenda-item"><div class="agenda-time">${escapeHTML(range(talk))}</div><div class="agenda-body"><h3>${escapeHTML(talk.title)}</h3><p class="session-meta">${escapeHTML(talk.speaker)} · ${escapeHTML(talk.level)} · ${escapeHTML(talk.room)}</p>${talk.reason ? `<p class="reason">Why: ${escapeHTML(talk.reason)}</p>` : ''}${sessionDetails(talk)}</div><button class="remove-button" type="button" data-remove="${escapeHTML(talk.id)}" aria-label="Remove ${escapeHTML(talk.title)}">×</button></article>`).join('') : '';
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
    const restored = !state.planDay;
    state.planDay = data.day || [...dates][0];
    if (restored) syncPlanDay(state.planDay);
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
  $('latest-empty').hidden = true;
  $('agenda-content').hidden = false;
  $('notice').hidden = true;
  state.ids = [...new Set(ids)];
  syncPlanDay(state.ids.length ? [...dates][0] || state.planDay : null);
  persist();
  updateCardButtons();
  renderSaveState();
  checkAgenda();
}

$('search-form').addEventListener('submit', (event) => { event.preventDefault(); search(); });
$('browse-program').addEventListener('click', openProgramme);
$('programme-drawer').addEventListener('toggle', () => { if ($('programme-drawer').open && !state.searchResults.length && !$('talks').getAttribute('aria-busy').includes('true')) search(); });
$('show-retained-draft').addEventListener('click', () => {
  $('agenda-content').hidden = false;
  document.querySelector('.agenda-save').hidden = !state.ids.length;
  $('show-retained-draft').hidden = true;
});
$('conference-day').addEventListener('change', () => {
  if (!state.ids.length) renderAgenda([]);
  if ($('programme-drawer').open && !state.planDay) search();
});

['track','level','captioned'].forEach((id) => $(id).addEventListener('change', search));
$('smart-search').addEventListener('change', search);
$('reset-filters').addEventListener('click', () => { $('track').value = ''; $('level').value = ''; $('captioned').checked = false; $('query').value = ''; search(); });
async function explainMatch(button) {
  const panel = button.closest('.match-tools').querySelector('.match-explanation');
  const query = (button.dataset.evidenceQuery ?? state.query).trim();
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
  const explain = event.target.closest('[data-explain]');
  if (explain) { explainMatch(explain); return; }
  const button = event.target.closest('[data-remove]');
  if (button) changeAgenda(state.ids.filter((id) => id !== button.dataset.remove));
});
$('conflicts').addEventListener('click', (event) => {
  const button = event.target.closest('[data-replace]');
  if (button) changeAgenda(state.ids.map((id) => id === button.dataset.replace ? button.dataset.with : id));
});
$('clear-agenda').addEventListener('click', () => {
  exitConference();
  state.draftEpoch += 1;
  state.origin = 'new'; setEditingPlan(); changeAgenda([]);
  $('request-editor').open = true;
  $('interests').value = ''; $('query').value = '';
  $('track').value = ''; $('level').value = ''; $('captioned').checked = false;
  state.searchResults = []; state.searchTotal = 0; $('talks').innerHTML = '';
  ['day-source', 'day-interpretation', 'day-selection-note'].forEach((id) => { $(id).hidden = true; });
  $('programme-drawer').open = false;
  notify('Agenda cleared. Make room for something new.');
});
$('check-agenda').addEventListener('click', () => checkAgenda(true));
$('day-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const interests = $('interests').value.trim();
  if (!interests) { notify('Add an interest or two so we can find your talks.', true); $('interests').focus(); return; }
  const button = $('build-button');
  const markers = new Set([...interests.matchAll(/\bday\s*([123])\b/gi)].map((match) => match[1]));
  if (markers.size > 1) { $('plan-scope').value = 'conference'; updateScope(); }
  const requestedScope = $('plan-scope').value;
  button.disabled = true;
  button.textContent = 'Finding your day…';
  const revision = state.agendaRevision;
  const requestedDay = $('conference-day').value;
  try {
    const data = requestedScope === 'conference'
      ? await post('/api/build-conference', {interests, captioned_only:$('day-captioned').checked, mode:'auto'})
      : await post('/api/build-my-day', {interests, smart:$('smart-day').checked, day:requestedDay, captioned_only:$('day-captioned').checked, mode:'auto'});
    if (revision !== state.agendaRevision || $('plan-scope').value !== requestedScope || (requestedScope === 'day' && $('conference-day').value !== requestedDay) || $('interests').value.trim() !== interests) {
      notify('Your day or request changed while planning. Your current choices were kept. Build again when ready.');
      return;
    }
    if (requestedScope === 'conference') { renderConference(data); return; }
    exitConference();
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
    state.draftEpoch += 1;
    $('request-editor').open = false;
    setEditingPlan();
    $('plan-name').value = `${dayLabel(data.day)} · ${(data.interests || 'Conference day').replace(/\b\w/g, (c) => c.toUpperCase())}`.slice(0,80);
    changeAgenda(data.talks.map((talk) => talk.id));
    const builtDayLabel = dayLabel(data.day);
    notify(`Your ${builtDayLabel} is ready: ${data.talks.length} relevant talks${data.max_talks !== null && data.max_talks !== undefined ? ` (maximum ${data.max_talks})` : ''}, without the clashes.${data.effective_level ? ` Experience: ${experienceLabel(data.effective_level)}.` : ''} You can still make it yours.`);
    $('agenda-title').focus({preventScroll:true});
  } catch (error) { notify(error.message, true); }
  finally { button.disabled = false; updateScope(); }
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
if (state.ids.length) { notify('Restored your previous agenda from this browser. Choose Clear to start fresh.'); checkAgenda(); }
