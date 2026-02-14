(function () {
  const API_BASE = '';
  const DEMO_AGENT_URLS = {
    calculator: 'http://localhost:8001',
    textProcessor: 'http://localhost:8002',
    weather: 'http://localhost:8003',
  };

  function getToken() {
    return sessionStorage.getItem('token');
  }

  function setToken(token) {
    if (token) sessionStorage.setItem('token', token);
    else sessionStorage.removeItem('token');
    updateLoginState();
  }

  function authHeaders() {
    const token = getToken();
    return token ? { Authorization: 'Bearer ' + token } : {};
  }

  async function api(method, path, body, useApiKey, apiKey) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (useApiKey && apiKey) {
      opts.headers['X-API-Key'] = apiKey;
    } else if (!useApiKey) {
      Object.assign(opts.headers, authHeaders());
    }
    if (body && method !== 'GET') opts.body = JSON.stringify(body);
    const res = await fetch(API_BASE + path, opts);
    let data;
    const ct = res.headers.get('content-type');
    if (ct && ct.includes('application/json')) {
      try { data = await res.json(); } catch (_) { data = null; }
    } else {
      data = await res.text();
    }
    if (!res.ok) throw { status: res.status, data };
    return data;
  }

  function show(el, text, isError) {
    if (typeof el === 'string') el = document.getElementById(el);
    if (!el) return;
    el.textContent = text || '';
    el.className = isError ? 'error' : 'success';
    el.style.display = text ? 'block' : 'none';
  }

  function updateLoginState() {
    const token = getToken();
    const state = document.getElementById('login-state');
    const email = document.getElementById('user-email');
    if (token) {
      state.style.display = 'block';
      api('GET', '/auth/me').then(u => { email.textContent = u.email || 'user'; }).catch(() => { email.textContent = 'user'; });
    } else {
      state.style.display = 'none';
    }
  }

  function switchSection(id) {
    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
    const section = document.getElementById('section-' + id);
    const btn = document.querySelector('nav button[data-section="' + id + '"]');
    if (section) section.classList.add('active');
    if (btn) btn.classList.add('active');
    if (id === 'integrations') loadIntegrations();
    if (id === 'agents') { loadMyAgents(); }
    if (id === 'logs') document.getElementById('logs-list').innerHTML = '';
  }

  document.querySelectorAll('nav button').forEach(btn => {
    btn.addEventListener('click', () => switchSection(btn.dataset.section));
  });

  document.getElementById('logout-btn').addEventListener('click', () => {
    setToken(null);
  });

  document.getElementById('form-register').addEventListener('submit', async e => {
    e.preventDefault();
    try {
      await api('POST', '/auth/register', {
        email: document.getElementById('reg-email').value,
        password: document.getElementById('reg-password').value,
        first_name: document.getElementById('reg-first').value || undefined,
        last_name: document.getElementById('reg-last').value || undefined,
      });
      show('reg-msg', 'Registered. You can now log in.', false);
      document.getElementById('reg-password').value = '';
    } catch (err) {
      show('reg-msg', err.data?.detail || err.data || 'Registration failed', true);
    }
  });

  document.getElementById('form-login').addEventListener('submit', async e => {
    e.preventDefault();
    try {
      const res = await api('POST', '/auth/login', {
        email: document.getElementById('login-email').value,
        password: document.getElementById('login-password').value,
      });
      setToken(res.access_token);
      show('login-msg', 'Logged in.', false);
      document.getElementById('login-password').value = '';
    } catch (err) {
      show('login-msg', err.data?.detail || err.data || 'Login failed', true);
    }
  });

  document.getElementById('form-create-integration').addEventListener('submit', async e => {
    e.preventDefault();
    const name = document.getElementById('int-name').value.trim();
    const kind = document.getElementById('int-kind').value.trim() || undefined;
    try {
      await api('POST', '/integrations', { name, kind });
      show('int-msg', 'Integration created.', false);
      document.getElementById('int-name').value = '';
      document.getElementById('int-kind').value = '';
      loadIntegrations();
    } catch (err) {
      show('int-msg', err.data?.detail || err.data || 'Failed', true);
    }
  });

  async function loadIntegrations() {
    const el = document.getElementById('integrations-list');
    try {
      const list = await api('GET', '/integrations');
      if (!list || !list.length) {
        el.innerHTML = '<p class="info">No integrations yet.</p>';
        return;
      }
      el.innerHTML = list.map(int => {
        const hasKey = int.has_api_key ? ' (has key)' : '';
        return `<div style="margin-bottom:1rem; padding:0.75rem; border:1px solid #eee; border-radius:4px;">
          <strong>${int.name}</strong> ${int.kind ? '(' + int.kind + ')' : ''}${hasKey} — ID: ${int.id}
          <br><button onclick="window.createIntKey('${int.id}')">Create API Key</button>
          <button onclick="window.deleteIntegration('${int.id}')">Delete</button>
        </div>`;
      }).join('');
    } catch (err) {
      el.innerHTML = '<p class="error">' + (err.data?.detail || 'Failed to load') + '</p>';
    }
  }

  window.createIntKey = async function (integrationId) {
    const name = prompt('API key name?', 'Demo Key') || 'Demo Key';
    try {
      const res = await api('POST', '/integrations/' + integrationId + '/api-keys', { name });
      alert('API Key (save it – shown only once):\n\n' + res.key);
      loadIntegrations();
    } catch (err) {
      alert(err.data?.detail || 'Failed');
    }
  };

  window.deleteIntegration = async function (id) {
    if (!confirm('Delete this integration?')) return;
    try {
      await api('DELETE', '/integrations/' + id);
      loadIntegrations();
    } catch (err) {
      alert(err.data?.detail || 'Failed');
    }
  };

  document.getElementById('form-register-agent').addEventListener('submit', async e => {
    e.preventDefault();
    let manifest;
    try {
      manifest = JSON.parse(document.getElementById('agent-manifest').value);
    } catch (_) {
      show('agent-msg', 'Invalid JSON', true);
      return;
    }
    try {
      const res = await api('POST', '/registry/agents', { manifest });
      show('agent-msg', 'Agent registered: ' + res.agent_id, false);
      loadMyAgents();
    } catch (err) {
      show('agent-msg', err.data?.detail || err.data || 'Failed', true);
    }
  });

  document.getElementById('form-discover').addEventListener('submit', async e => {
    e.preventDefault();
    const query = document.getElementById('discover-query').value.trim();
    const el = document.getElementById('discover-results');
    if (!query) return;
    try {
      const list = await api('GET', '/registry/discover?query=' + encodeURIComponent(query) + '&limit=10');
      if (!list || !list.length) {
        el.innerHTML = '<p class="info">No agents found.</p>';
        return;
      }
      el.innerHTML = '<pre>' + JSON.stringify(list, null, 2) + '</pre>';
    } catch (err) {
      el.innerHTML = '<p class="error">' + (err.data?.detail || 'Failed') + '</p>';
    }
  });

  async function loadMyAgents() {
    const el = document.getElementById('agents-list');
    try {
      const list = await api('GET', '/registry/my-agents');
      if (!list || !list.length) {
        el.innerHTML = '<p class="info">No agents yet.</p>';
        return;
      }
      el.innerHTML = '<table><tr><th>Agent ID</th><th>Name</th><th>Version</th></tr>' +
        list.map(a => `<tr><td>${a.agent_id}</td><td>${a.name}</td><td>${a.version}</td></tr>`).join('') +
        '</table>';
    } catch (err) {
      el.innerHTML = '<p class="error">' + (err.data?.detail || 'Failed') + '</p>';
    }
  }

  document.getElementById('form-create-task').addEventListener('submit', async e => {
    e.preventDefault();
    const apiKey = document.getElementById('task-api-key').value.trim();
    const goal = document.getElementById('task-goal').value.trim();
    let input = {};
    try {
      input = JSON.parse(document.getElementById('task-input').value || '{}');
    } catch (_) {}
    const msgEl = document.getElementById('task-msg');
    const resultEl = document.getElementById('task-result');
    if (!apiKey) {
      show('task-msg', 'Enter an API key.', true);
      return;
    }
    try {
      const res = await api('POST', '/tasks', { goal, input }, true, apiKey);
      resultEl.innerHTML = '<h4>Task Result</h4><pre>' + JSON.stringify(res, null, 2) + '</pre>';
      if (res.task_id) {
        const taskRes = await api('GET', '/tasks/' + res.task_id, null, true, apiKey);
        resultEl.innerHTML += '<h4>Task Details</h4><pre>' + JSON.stringify(taskRes, null, 2) + '</pre>';
      }
      show('task-msg', '', false);
    } catch (err) {
      show('task-msg', err.data?.detail || err.data || 'Failed', true);
      resultEl.innerHTML = '';
    }
  });

  document.getElementById('btn-generate-demo').addEventListener('click', async () => {
    const btn = document.getElementById('btn-generate-demo');
    const msgEl = document.getElementById('generate-msg');
    const keyEl = document.getElementById('generate-api-key');
    const keySpan = document.getElementById('generated-key');
    btn.disabled = true;
    show('generate-msg', 'Creating account...', false);
    const ts = Date.now();
    const email = 'demo_' + ts + '@example.com';
    const password = 'demo_password_123';
    try {
      await api('POST', '/auth/register', { email, password, first_name: 'Demo', last_name: 'User' });
      show('generate-msg', 'Logging in...', false);
      const loginRes = await api('POST', '/auth/login', { email, password });
      setToken(loginRes.access_token);
      show('generate-msg', 'Creating integration...', false);
      const intRes = await api('POST', '/integrations', { name: 'Demo Integration', kind: 'demo' });
      show('generate-msg', 'Creating API key...', false);
      const keyRes = await api('POST', '/integrations/' + intRes.id + '/api-keys', { name: 'Demo Key' });
      show('generate-msg', 'Registering agents...', false);
      const calc = getCalculatorManifest();
      const text = getTextProcessorManifest();
      const weather = getWeatherManifest();
      await api('POST', '/registry/agents', { manifest: calc });
      await api('POST', '/registry/agents', { manifest: text });
      await api('POST', '/registry/agents', { manifest: weather });
      keySpan.textContent = keyRes.key;
      keyEl.style.display = 'block';
      show('generate-msg', 'Demo created successfully.', false);
      loadIntegrations();
      loadMyAgents();
    } catch (err) {
      show('generate-msg', err.data?.detail || err.data || 'Failed', true);
      keyEl.style.display = 'none';
    }
    btn.disabled = false;
  });

  document.getElementById('copy-api-key').addEventListener('click', () => {
    const key = document.getElementById('generated-key').textContent;
    navigator.clipboard.writeText(key).then(() => alert('Copied!')).catch(() => {});
  });

  function getCalculatorManifest() {
    return {
      agent_id: 'agent:demo:calculator:1.0.0',
      name: 'Calculator Agent',
      description: 'A simple calculator agent that performs basic mathematical operations like addition, subtraction, and multiplication',
      version: '1.0.0',
      endpoints: { invoke: DEMO_AGENT_URLS.calculator + '/invoke' },
      capabilities: [
        { id: 'add', input_schema: { type: 'object', properties: { a: { type: 'number' }, b: { type: 'number' } }, required: ['a', 'b'] }, output_schema: { type: 'object', properties: { result: { type: 'number' } } }, auth_type: { type: 'public' } },
        { id: 'subtract', input_schema: { type: 'object', properties: { a: { type: 'number' }, b: { type: 'number' } }, required: ['a', 'b'] }, output_schema: { type: 'object', properties: { result: { type: 'number' } } }, auth_type: { type: 'public' } },
        { id: 'multiply', input_schema: { type: 'object', properties: { a: { type: 'number' }, b: { type: 'number' } }, required: ['a', 'b'] }, output_schema: { type: 'object', properties: { result: { type: 'number' } } }, auth_type: { type: 'public' } },
      ],
      tags: ['math', 'calculator', 'arithmetic'],
      trust: { verification: 'self-signed' },
    };
  }

  function getTextProcessorManifest() {
    return {
      agent_id: 'agent:demo:text-processor:1.0.0',
      name: 'Text Processor Agent',
      description: 'A text processing agent that can convert text to uppercase, lowercase, and reverse strings',
      version: '1.0.0',
      endpoints: { invoke: DEMO_AGENT_URLS.textProcessor + '/invoke' },
      capabilities: [
        { id: 'uppercase', input_schema: { type: 'object', properties: { text: { type: 'string' } }, required: ['text'] }, output_schema: { type: 'object', properties: { result: { type: 'string' } } }, auth_type: { type: 'public' } },
        { id: 'lowercase', input_schema: { type: 'object', properties: { text: { type: 'string' } }, required: ['text'] }, output_schema: { type: 'object', properties: { result: { type: 'string' } } }, auth_type: { type: 'public' } },
        { id: 'reverse', input_schema: { type: 'object', properties: { text: { type: 'string' } }, required: ['text'] }, output_schema: { type: 'object', properties: { result: { type: 'string' } } }, auth_type: { type: 'public' } },
      ],
      tags: ['text', 'processing', 'string', 'nlp'],
      trust: { verification: 'self-signed' },
    };
  }

  function getWeatherManifest() {
    return {
      agent_id: 'agent:demo:weather:1.0.0',
      name: 'Weather Agent',
      description: 'A weather agent that provides weather information for cities',
      version: '1.0.0',
      endpoints: { invoke: DEMO_AGENT_URLS.weather + '/invoke' },
      capabilities: [
        { id: 'get_weather', input_schema: { type: 'object', properties: { city: { type: 'string' } }, required: ['city'] }, output_schema: { type: 'object', properties: { city: {}, temperature: {}, condition: {}, humidity: {}, unit: {} } }, auth_type: { type: 'public' } },
      ],
      tags: ['weather', 'forecast', 'city'],
      trust: { verification: 'self-signed' },
    };
  }

  document.getElementById('form-invoke').addEventListener('submit', async e => {
    e.preventDefault();
    const apiKey = document.getElementById('invoke-api-key').value.trim();
    const agentId = document.getElementById('invoke-agent-id').value.trim();
    const capabilityId = document.getElementById('invoke-capability').value.trim();
    let input;
    try {
      input = JSON.parse(document.getElementById('invoke-input').value || '{}');
    } catch (_) {
      document.getElementById('invoke-result').innerHTML = '<p class="error">Invalid JSON input</p>';
      return;
    }
    if (!apiKey || !agentId || !capabilityId) {
      document.getElementById('invoke-result').innerHTML = '<p class="error">Fill all fields</p>';
      return;
    }
    try {
      const res = await api('POST', '/broker/invoke', { agent_id: agentId, capability_id: capabilityId, input }, true, apiKey);
      document.getElementById('invoke-result').innerHTML = '<pre>' + JSON.stringify(res, null, 2) + '</pre>';
    } catch (err) {
      document.getElementById('invoke-result').innerHTML = '<p class="error">' + (err.data?.detail || err.data || 'Failed') + '</p>';
    }
  });

  document.getElementById('btn-load-logs').addEventListener('click', async () => {
    const el = document.getElementById('logs-list');
    try {
      const list = await api('GET', '/broker/logs?limit=50');
      if (!list || !list.length) {
        el.innerHTML = '<p class="info">No logs.</p>';
        return;
      }
      el.innerHTML = '<table><tr><th>Time</th><th>Agent</th><th>Capability</th><th>Status</th><th>Latency</th></tr>' +
        list.map(log => `<tr><td>${log.created_at}</td><td>${log.target_agent_id}</td><td>${log.capability_id}</td><td>${log.status_code}</td><td>${log.latency_ms}ms</td></tr>`).join('') +
        '</table>';
    } catch (err) {
      el.innerHTML = '<p class="error">' + (err.data?.detail || 'Failed') + '</p>';
    }
  });

  updateLoginState();
  switchSection('auth');
})();
