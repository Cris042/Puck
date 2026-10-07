// Cenário de carga (protocolo 4.5): idêntico para todas as células, dados criados pelo contrato.
// Duas cargas simultâneas sobre uma turma de 30 alunos:
//   leitura — professor consulta o boletim da disciplina;
//   escrita — professor lança o lote de notas dos 30 alunos.
// Ambiente: TARGET_URL, PUCK_BOOTSTRAP_{EMAIL,MATRICULA,SENHA}, DURACAO, VUS_LEITURA, VUS_ESCRITA.
import http from 'k6/http';
import { check, fail } from 'k6';

const BASE = __ENV.TARGET_URL;
const DURACAO = __ENV.DURACAO || '30s';
const JSON_HEADERS = { 'Content-Type': 'application/json', Accept: 'application/json' };
const ALUNOS = 30;

export const options = {
  scenarios: {
    leitura: { executor: 'constant-vus', exec: 'leitura', vus: Number(__ENV.VUS_LEITURA || 7), duration: DURACAO, tags: { cenario: 'leitura' } },
    escrita: { executor: 'constant-vus', exec: 'escrita', vus: Number(__ENV.VUS_ESCRITA || 3), duration: DURACAO, tags: { cenario: 'escrita' } },
  },
  // Limiares sempre verdadeiros: só servem para o k6 calcular as submétricas por cenário.
  thresholds: {
    'http_req_duration{cenario:leitura}': ['p(95)>=0'],
    'http_req_duration{cenario:escrita}': ['p(95)>=0'],
    'http_req_failed{cenario:leitura}': ['rate>=0'],
    'http_req_failed{cenario:escrita}': ['rate>=0'],
  },
  summaryTrendStats: ['med', 'p(95)', 'max'],
};

function sufixo() {
  return `${Date.now()}${Math.floor(Math.random() * 1e6)}`;
}

function criar(caminho, corpo, cookies) {
  const resposta = http.post(`${BASE}${caminho}`, JSON.stringify(corpo), { headers: JSON_HEADERS, cookies, tags: { cenario: 'setup' } });
  if (resposta.status !== 201) fail(`${caminho}: ${resposta.status} ${resposta.body}`);
  return resposta.json();
}

function entrar(email, matricula, senha) {
  const jar = http.cookieJar();
  const resposta = http.post(`${BASE}/api/sessao`, JSON.stringify({ email, matricula, senha }), { headers: JSON_HEADERS, tags: { cenario: 'setup' } });
  if (resposta.status !== 200) fail(`login: ${resposta.status} ${resposta.body}`);
  const cookies = {};
  for (const [nome, valores] of Object.entries(jar.cookiesForURL(BASE))) cookies[nome] = valores[0];
  return cookies;
}

export function setup() {
  const sec = entrar(__ENV.PUCK_BOOTSTRAP_EMAIL, __ENV.PUCK_BOOTSTRAP_MATRICULA, __ENV.PUCK_BOOTSTRAP_SENHA);
  const s = sufixo();
  const curso = criar('/api/cursos', { nome: `Curso carga ${s}` }, sec).id;
  const serie = criar('/api/series', { nome: `Serie carga ${s}` }, sec).id;
  const turma = criar('/api/turmas', { ano: '2026', curso_id: curso, serie_id: serie }, sec).id;
  const senha = 'senha-sintetica-carga';
  const professor = criar('/api/professores', { nome: 'Professor carga', email: `prof${s}@exemplo.test`, matricula: `PC${s}`, senha }, sec);
  const disciplina = criar(`/api/turmas/${turma}/disciplinas`, { nome: `Disciplina ${s}`, professor_id: professor.id, carga_horaria: 80 }, sec).id;
  const alunos = [];
  for (let i = 0; i < ALUNOS; i++) {
    const aluno = criar('/api/alunos', { nome: `Aluno carga ${i}`, email: `aluno${i}.${s}@exemplo.test`, matricula: `AC${s}${i}`, senha }, sec);
    criar(`/api/turmas/${turma}/matriculas`, { aluno_id: aluno.id }, sec);
    alunos.push(aluno.id);
  }
  return { disciplina, alunos, cookies: entrar(professor.email, professor.matricula, senha) };
}

export function leitura(dados) {
  const resposta = http.get(`${BASE}/api/disciplinas/${dados.disciplina}/boletim`, { headers: JSON_HEADERS, cookies: dados.cookies });
  check(resposta, { 'boletim 200': (r) => r.status === 200 });
}

export function escrita(dados) {
  const nota = () => Math.floor(Math.random() * 101);
  const lancamentos = dados.alunos.map((aluno_id) => ({ aluno_id, notas: [nota(), nota(), nota(), nota()], recuperacoes: [null, null, null, null] }));
  const resposta = http.put(`${BASE}/api/disciplinas/${dados.disciplina}/notas`, JSON.stringify({ lancamentos }), { headers: JSON_HEADERS, cookies: dados.cookies });
  check(resposta, { 'notas 200': (r) => r.status === 200 });
}

function ms(valor) {
  return Math.round(valor || 0);
}

export function handleSummary(data) {
  const m = data.metrics;
  const linhas = [];
  for (const cenario of ['leitura', 'escrita']) {
    const duracao = m[`http_req_duration{cenario:${cenario}}`];
    const falhas = m[`http_req_failed{cenario:${cenario}}`];
    if (!duracao) continue;
    linhas.push(`PUCK_METRIC carga_${cenario}_p50_ms ${ms(duracao.values.med)}`);
    linhas.push(`PUCK_METRIC carga_${cenario}_p95_ms ${ms(duracao.values['p(95)'])}`);
    linhas.push(`PUCK_METRIC carga_${cenario}_max_ms ${ms(duracao.values.max)}`);
    linhas.push(`PUCK_METRIC carga_${cenario}_falhas_permil ${Math.round((falhas ? falhas.values.rate : 0) * 1000)}`);
  }
  linhas.push(`PUCK_METRIC carga_requisicoes ${m.http_reqs ? m.http_reqs.values.count : 0}`);
  linhas.push(`PUCK_METRIC carga_req_por_s_x100 ${Math.round((m.http_reqs ? m.http_reqs.values.rate : 0) * 100)}`);
  return { stdout: linhas.join('\n') + '\n' };
}
