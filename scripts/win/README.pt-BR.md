# Scripts de apoio para Windows

Scripts PowerShell para colaboradores no Windows (tradutores / quem compila o jogo).
Eles reproduzem o fluxo de trabalho do Linux (`uv sync` + `scripts/build.sh`).

> Para o tradutor: estes três scripts preparam tudo o que você precisa para editar o
> texto e gerar a ROM em inglês/português. Você **não** precisa saber programar — basta
> executar `setup` uma vez e depois usar `run-editor` para traduzir.

| Script | Para que serve |
|---|---|
| `setup.ps1` | Preparação do ambiente (rode **uma vez**): instala o `uv`, baixa uma versão compatível do Python (CPython), cria a `.venv` e instala todas as dependências. |
| `run-editor.ps1` | Abre o editor de tradução (`script_editor.py`), com pré-visualização ao vivo usando a fonte do jogo. |
| `build.ps1` | Compila `out\rbshura_br_pt.sfc` (+ `.ips`/`.xdelta`) e roda a verificação de gravação (audit gate). Aceita `-Patcher` e `-UpdateAudit`. |

## Como executar

**Mais fácil — dê um duplo-clique no arquivo `.cmd`** (`setup.cmd`, `run-editor.cmd`,
`build.cmd`). Cada wrapper executa o `.ps1` correspondente com a política de execução
liberada **apenas para aquela execução** (não altera a política global da sua máquina).

Ou rode o `.ps1` diretamente, liberando a política por execução:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\win\setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\win\run-editor.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\win\build.ps1
```

O `build.ps1` aceita as mesmas opções do `build.sh`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\win\build.ps1 -Patcher
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\win\build.ps1 -UpdateAudit
```

## Fluxo de tradução (passo a passo)

1. Rode `setup.cmd` **uma vez** para preparar o ambiente.
2. Abra `run-editor.cmd`. No editor, aponte a pasta de origem para **`data\br_pt`**
   (botão de configurações / seleção de pasta) — é onde fica o roteiro em português.
3. Os arquivos de texto ficam em `data\br_pt\` e **já estão todos disponíveis** no editor:
   os 15 roteiros (`scenario_00`…`scenario_28`), os nomes de HUD (`char_names`), a
   abertura (`intro`) e as telas de narração de final (`narration_screens`).
   No começo eles contêm o texto **em inglês** — basta substituir pelo português.
4. As letras acentuadas do português (`Éáéíóúâêôàãõç`) já existem na fonte e na
   tabela `tables/rbshura_br_pt.tbl`. Pode digitá-las normalmente.
5. Quando quiser ver o resultado no jogo, rode `build.cmd` e abra
   `out\rbshura_br_pt.sfc` num emulador (Mesen, Snes9x, bsnes).

> Você pode mudar o tamanho dos textos à vontade: os roteiros são alocados
> automaticamente no espaço livre da ROM, então textos mais longos **não** exigem
> mexer em nenhuma configuração. (Exceções: a abertura `intro` e as telas
> `narration_screens` ocupam regiões de tamanho limitado — se estourarem, avise o
> autor do projeto.)

## O que precisa ser localizado

Tudo o que muda para traduzir o jogo está em poucos lugares:

| O quê | Onde | Observações |
|---|---|---|
| **Texto do roteiro** (todo o texto do jogo) | `data\br_pt\` | Os 15 roteiros (`scenario_00`…`scenario_28`), nomes de HUD (`char_names`), abertura (`intro`) e telas de narração de final (`narration_screens`). Todos editáveis no editor. |
| **Placas de golpes especiais** (arte) | `export\attack_names\*_br_pt.png` | Redesenhar os nomes dos golpes (ex.: "Dragon Wave"). Cópias em português dos `*_en.png`. Trabalho de imagem. |
| **Arte do título "SHURA"** | `export\title_kanji_br_pt_expanded.png` | Kanji grande do título (sprites). |
| **Logo "RUSHING BEAT"** | `export\title_bg1_logo_br_pt.png` | Arte do logo do título (BG1). |

Editar esses quatro itens é **tudo o que normalmente é preciso** para gerar o jogo em
outro idioma. As imagens já têm cópias `_br_pt` (iguais às `_en` no início, como ponto
de partida) — o `project.toml` escolhe a versão certa pelo idioma do build (`${lang}`),
então é só editar os arquivos `_br_pt`. O crédito da tradução na tela de abertura fica em
`patches\intro_credit.asm` (fonte só em MAIÚSCULAS ASCII, sem acentos).

> **Vai renomear algum arquivo?** A compilação localiza os arquivos por nome/caminho.
> Se você **renomear** um arquivo, atualize quem o referencia:
> - Tabela renomeada (`tables\*.tbl`) → atualize `table_file = "..."` em cada
>   `tables\scenario_*.toml` que a usa.
> - Imagem / fonte renomeada → atualize o `file = "..."` da seção correspondente em
>   `project.toml`.
> - Arquivo de texto renomeado → o nome (sem extensão) precisa continuar batendo com o
>   `name =` do `tables\*.toml` correspondente.

## Pré-requisitos / observações

- **ROM original.** O `build.ps1` precisa da ROM japonesa original em
  `roms\rbshura.sfc` (não incluída no repositório, por direitos autorais). O editor e
  a compilação não funcionam sem ela.
- **Dependência do retrotool.** O `pyproject.toml` aponta o motor de compilação
  `retrotool` para uma cópia local (um caminho absoluto que só existe na máquina do
  autor). Numa máquina Windows nova, o `uv sync` não consegue resolvê-lo até você
  apontar para a sua própria cópia do retrotool:

  ```powershell
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\win\setup.ps1 -RetrotoolPath C:\caminho\para\retrotool
  ```

  Isso reescreve `[tool.uv.sources]` no `pyproject.toml` apontando para a sua cópia
  (um backup é salvo em `pyproject.toml.bak`).
