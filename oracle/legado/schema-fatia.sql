-- Tabelas da fatia vertical, na ordem de colunas exigida pelos INSERT posicionais do código fixado
-- (docs/legado/MER_DER.md, seção 3). Tipos: TEXTO, por suposição declarada — o tipo real das
-- colunas de 2024 é desconhecido e decide arredondamento (no dump de 2020, notas.media era INT).
-- Com texto, o banco guarda exatamente o valor que o PHP calculou: o dourado caracteriza a REGRA.
CREATE TABLE diciplina (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nome VARCHAR(255) NOT NULL DEFAULT '',
  cod_ano VARCHAR(255) NOT NULL DEFAULT '',
  cod_curso VARCHAR(255) NOT NULL DEFAULT '',
  cod_serie VARCHAR(255) NOT NULL DEFAULT '',
  cod_professo VARCHAR(255) NOT NULL DEFAULT '',
  carga_horaria VARCHAR(255) NOT NULL DEFAULT ''
);

CREATE TABLE matriculados (
  id INT AUTO_INCREMENT PRIMARY KEY,
  cod_curso VARCHAR(255) NOT NULL DEFAULT '',
  cod_serie VARCHAR(255) NOT NULL DEFAULT '',
  cod_ano VARCHAR(255) NOT NULL DEFAULT '',
  cod_aluno VARCHAR(255) NOT NULL DEFAULT '',
  nome VARCHAR(255) NOT NULL DEFAULT '',
  dependencia INT NOT NULL DEFAULT 0
);

CREATE TABLE notas (
  cod_aluno VARCHAR(255) NOT NULL DEFAULT '',
  cod_curso VARCHAR(255) NOT NULL DEFAULT '',
  cod_serie VARCHAR(255) NOT NULL DEFAULT '',
  cod_ano VARCHAR(255) NOT NULL DEFAULT '',
  cod_diciplina VARCHAR(255) NOT NULL DEFAULT '',
  cod_professo VARCHAR(255) NOT NULL DEFAULT '',
  n1 VARCHAR(255) NOT NULL DEFAULT '',
  r1 VARCHAR(255) NOT NULL DEFAULT '',
  n2 VARCHAR(255) NOT NULL DEFAULT '',
  r2 VARCHAR(255) NOT NULL DEFAULT '',
  n3 VARCHAR(255) NOT NULL DEFAULT '',
  r3 VARCHAR(255) NOT NULL DEFAULT '',
  n4 VARCHAR(255) NOT NULL DEFAULT '',
  r4 VARCHAR(255) NOT NULL DEFAULT '',
  media VARCHAR(255) NOT NULL DEFAULT '',
  aprovado VARCHAR(255) NOT NULL DEFAULT '',
  nota01 VARCHAR(255) NOT NULL DEFAULT '',
  nota02 VARCHAR(255) NOT NULL DEFAULT '',
  nota03 VARCHAR(255) NOT NULL DEFAULT '',
  nota04 VARCHAR(255) NOT NULL DEFAULT '',
  media_parcial VARCHAR(255) NOT NULL DEFAULT '',
  atrasada_nota01 VARCHAR(255) NOT NULL DEFAULT '',
  atrasada_nota02 VARCHAR(255) NOT NULL DEFAULT '',
  atrasada_nota03 VARCHAR(255) NOT NULL DEFAULT '',
  atasada_nota04 VARCHAR(255) NOT NULL DEFAULT '',
  PRIMARY KEY (cod_aluno, cod_curso, cod_serie, cod_ano, cod_diciplina, cod_professo)
);

CREATE TABLE presenca (
  id INT AUTO_INCREMENT PRIMARY KEY,
  cod_aluno VARCHAR(255) NOT NULL DEFAULT '',
  cod_professo VARCHAR(255) NOT NULL DEFAULT '',
  cod_curso VARCHAR(255) NOT NULL DEFAULT '',
  cod_serie VARCHAR(255) NOT NULL DEFAULT '',
  cod_ano VARCHAR(255) NOT NULL DEFAULT '',
  cod_materia VARCHAR(255) NOT NULL DEFAULT '',
  faltas VARCHAR(255) NOT NULL DEFAULT '',
  data VARCHAR(255) NOT NULL DEFAULT '',
  bimestre VARCHAR(255) NOT NULL DEFAULT ''
);
