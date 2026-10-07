-- Atena — dump MariaDB de 10/09/2020 (banco `sistema`), SOMENTE ESTRUTURA.
--
-- Proveniência: phpMyAdmin 5.0.2, MariaDB 10.4.11, fornecido pelo autor em 2026-10-07.
-- Os INSERTs do dump original foram REMOVIDOS: continham dados pessoais reais (nomes, CPF, e-mail,
-- telefone, filiação, hash md5 de senha). O protocolo exige dados 100% sintéticos; nada daquele
-- conteúdo pode entrar em prompt, índice RAG ou repositório.
--
-- ATENÇÃO: este NÃO é o schema usado pelo código fixado do Atena (ac48dc5, 2024). É uma versão
-- anterior do sistema, com outro modelo (tabela única `user`, biblioteca, eventos, tracking).
-- Serve como registro histórico e como pista de tipos (ex.: notas como INT). O schema efetivo do
-- commit fixado está descrito em docs/legado/MER_DER.md.

CREATE TABLE `arquivos` (
  `id` int(11) NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `idTurma` int(11) NOT NULL,
  `idProf` int(11) NOT NULL,
  `nome` varchar(124) NOT NULL,
  `data` date NOT NULL,
  `arquivo` varchar(124) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `atividades` (
  `id` int(11) NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `idTurma` int(11) NOT NULL,
  `IdProf` int(11) NOT NULL,
  `idAluno` int(11) NOT NULL,
  `matter` varchar(124) NOT NULL,
  `nome` varchar(124) NOT NULL,
  `data` date NOT NULL,
  `dataEntrega` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `calendario` (
  `id` int(11) NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `conteudo` varchar(124) NOT NULL,
  `data` date NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `chat` (
  `id` int(11) NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `idSender` int(11) NOT NULL,
  `idDestiny` int(11) NOT NULL,
  `messagem` varchar(124) NOT NULL,
  `vizualizada` int(11) NOT NULL,
  `data` date NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `curso` (
  `id` int(11) NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `nome` varchar(124) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `diario` (
  `id` int(11) NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `periodo01` date NOT NULL,
  `periodo02` date NOT NULL,
  `periodo03` date NOT NULL,
  `periodo04` date NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `diariocontroler` (
  `id` int(11) NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `idClass` int(11) NOT NULL,
  `bimestre` varchar(124) NOT NULL,
  `estado` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `emprestimolivros` (
  `id` int(11) NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `idUser` varchar(255) NOT NULL,
  `idLivro` int(11) NOT NULL,
  `nomeLivro` varchar(255) NOT NULL,
  `dataEmprestimo` varchar(16) NOT NULL,
  `dataValidade` varchar(16) NOT NULL,
  `estado` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `escolar` (
  `id` int(11) NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `nome` varchar(124) NOT NULL,
  `address` varchar(255) NOT NULL,
  `cnpj` varchar(32) NOT NULL,
  `diretor` varchar(124) NOT NULL,
  `telefone` varchar(20) NOT NULL,
  `telefoneSuporte` varchar(20) NOT NULL,
  `email` varchar(124) NOT NULL,
  `timeAluno` int(11) NOT NULL,
  `horarioAbertura` int(11) NOT NULL,
  `horarioFechamento` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `evento` (
  `id` int(11) NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `nome` varchar(124) NOT NULL,
  `data` date NOT NULL,
  `local` varchar(124) NOT NULL,
  `vagas` int(11) NOT NULL,
  `duracao` varchar(25) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `gradecurricular` (
  `id` int(11) NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `idTurma` varchar(255) NOT NULL,
  `grade` varchar(124) NOT NULL,
  `idProf` varchar(124) NOT NULL,
  `Ch` varchar(124) NOT NULL,
  `materia` varchar(124) NOT NULL,
  `estado` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `grades` (
  `id` int(11) NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `nome` varchar(124) NOT NULL,
  `materia` varchar(124) NOT NULL,
  `Ch` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `horaio` (
  `id` int(11) NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `idTurma` int(11) NOT NULL,
  `idProf` int(11) NOT NULL,
  `data` date NOT NULL,
  `dia` varchar(32) NOT NULL,
  `periodo` varchar(32) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `livros` (
  `id` int(11) NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `nome` varchar(124) NOT NULL,
  `autor` varchar(124) NOT NULL,
  `lancamento` date NOT NULL,
  `estoque` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `materia` (
  `id` int(11) NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `nome` varchar(64) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `matriculados` (
  `id` int(11) NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `idAluno` int(11) NOT NULL,
  `idTurma` int(11) NOT NULL,
  `estado` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `notas` (
  `id` int(11) NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `idTurma` int(11) NOT NULL,
  `idAluno` int(11) NOT NULL,
  `n1` int(11) NOT NULL,
  `n2` int(11) NOT NULL,
  `n3` int(11) NOT NULL,
  `n4` int(11) NOT NULL,
  `r1` int(11) NOT NULL,
  `r2` int(11) NOT NULL,
  `r3` int(11) NOT NULL,
  `r4` int(11) NOT NULL,
  `media` int(11) NOT NULL,
  `mediaParcial` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `participarevento` (
  `id` int(11) NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `idUser` int(11) NOT NULL,
  `idEvento` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `perguntas` (
  `id` int(11) NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `materia` varchar(124) NOT NULL,
  `conteudo` varchar(124) NOT NULL,
  `dificuldade` int(11) NOT NULL,
  `periodo` int(11) NOT NULL,
  `pergunta` varchar(255) NOT NULL,
  `resposta` varchar(255) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `presence` (
  `id` int(11) NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `idTurma` int(11) NOT NULL,
  `idProf` int(11) NOT NULL,
  `idMateria` int(11) NOT NULL,
  `idAluno` int(11) NOT NULL,
  `periodo` varchar(32) NOT NULL,
  `data` date NOT NULL,
  `faltas` int(11) NOT NULL,
  `conteudo` varchar(255) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `tarefas` (
  `id` int(11) NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `idAluno` int(11) NOT NULL,
  `idTurma` int(11) NOT NULL,
  `idMateria` int(11) NOT NULL,
  `idProf` int(11) NOT NULL,
  `nome` int(11) NOT NULL,
  `valor` int(11) NOT NULL,
  `valorObtido` int(11) NOT NULL,
  `periodo` varchar(32) NOT NULL,
  `estado` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `tracking` (
  `id` int(11) NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `idUser` int(11) NOT NULL,
  `ip` varchar(124) NOT NULL,
  `phone` varchar(124) NOT NULL,
  `date` date NOT NULL,
  `location` varchar(124) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `turmas` (
  `id` int(11) NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `idClass` varchar(255) NOT NULL,
  `ano` varchar(124) NOT NULL,
  `curso` varchar(114) NOT NULL,
  `periodo` varchar(124) NOT NULL,
  `complemento` varchar(124) NOT NULL,
  `grade` varchar(124) NOT NULL,
  `estado` int(11) NOT NULL,
  `block` int(11) NOT NULL,
  `senha` varchar(32) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `user` (
  `id` int(11) NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `cargo` int(11) NOT NULL,
  `solitacao` int(11) NOT NULL,
  `matricular` varchar(32) NOT NULL,
  `matriculado` int(11) NOT NULL,
  `nome` varchar(255) NOT NULL,
  `email` varchar(124) NOT NULL,
  `senha` varchar(124) NOT NULL,
  `hast` varchar(124) NOT NULL,
  `telefone` varchar(20) NOT NULL,
  `address` varchar(124) NOT NULL,
  `cpf` varchar(124) NOT NULL,
  `dataNacimento` date NOT NULL,
  `estadoCivil` varchar(32) NOT NULL,
  `sex` varchar(32) NOT NULL,
  `imagem` varchar(124) NOT NULL,
  `pai` varchar(124) DEFAULT NULL,
  `mae` varchar(124) DEFAULT NULL,
  `emailResponsavel` varchar(124) DEFAULT NULL,
  `telefoneResponsavel` varchar(20) DEFAULT NULL,
  `ativado` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
