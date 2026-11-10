# 📖 Manual do Usuário — Análise de Sítio (IngeTrazo)

Este manual detalha o funcionamento de cada uma das 12 seções do painel
"Análise de Sítio" e dos recursos que o acompanham (barra de ferramentas e
painéis flutuantes). Explica o que cada botão faz, como os dados são
calculados e como aproveitar melhor o plugin no dia a dia de projeto.

Ele complementa o `README_ptBR.md` (que descreve a instalação e a
arquitetura). Aqui o foco é **uso**.

---

## Visão geral rápida

- O plugin vive em **uma aba lateral** (12 seções recolhíveis) e em **uma
  barra de ferramentas** com 19 botões.
- Os dados climáticos vêm de um arquivo **EPW** (opcional, mas recomendado).
- A **data e a hora** usadas pelo plugin são as mesmas do painel de Sombras
  do IngeTrazo (uma única verdade).
- O plugin pode desenhar **dois painéis flutuantes arrastáveis** por cima da
  vista 3D:
  - **Análise de Sítio** — informações, convenções e clima na hora atual.
  - **Radiação / Sombras** — escala de cores dos mapas calculados.
- Todos os comandos que mudam o modelo (massas, lotes, contexto OSM, mapas
  de radiação/sombra) são **um passo de desfazer**.

### Exemplo rápido (10 minutos)

1. **Seção 1** → Abra um EPW de Belo Horizonte.
2. **Seção 2** → Confirme a localização (o EPW já preencheu).
3. **Seção 3** → Deixe o norte em 0°.
4. **Seção 8** → Desenhe o terreno no chão, selecione e clique em
   **Lote da seleção**.
5. Desenhe a planta do prédio, selecione e clique em **Massa da seleção**.
   Defina a altura em 12 m.
6. **Seção 4** → Escolha 21 de junho, 15h.
7. **Seção 11** → Período = "Ano completo", clique em **Calcular
   radiação**.
8. **Seção 12** → **Exportar imagem (PNG)**, 4K.
9. Salve a imagem em `Documentos`.

Pronto: você tem um diagnóstico solar do terreno e do prédio em uma
imagem pronta para apresentação.

---

## 1 · ☁ Carregar arquivo EPW

O arquivo **EPW** (EnergyPlus Weather) é a espinha dorsal de qualquer
análise climática. Ele contém dados horários de temperatura, umidade,
direção e velocidade do vento, além da radiação solar (DNI e DHI) de um
ano inteiro.

### O que os botões fazem

- **Abrir arquivo EPW…**: abre o diálogo na pasta **Downloads** do
  usuário. Ao carregar, o plugin:
  - extrai os dados horários;
  - salva uma **versão compacta** (≈ 400 kB) dentro do seu `.igz`;
  - descarta o que não será usado (por exemplo, 29 de fevereiro em anos
    bissextos);
  - **opcionalmente**, se a caixa abaixo estiver marcada, atualiza a
    localização do projeto a partir das coordenadas do EPW.
- **Usar a localização do EPW para o sítio**: se marcado, o plugin pega a
  latitude, longitude e o fuso horário (UTC) do arquivo e define como a
  localização do projeto no IngeTrazo (`scene.georef`). Útil quando você
  baixa um EPW de uma estação específica e quer que tudo (sol, sombras,
  mapa) se alinhe a ela automaticamente.
- **Período de análise**: recorta o ano para analisar apenas uma estação
  ou horário.
  - *Meses*: você pode cruzar o ano, por exemplo de novembro a fevereiro
    (verão).
  - *Horas*: pode analisar apenas o período diurno (8h às 18h) ou o
    noturno.
  - *Atenção*: este período é usado pelas **estatísticas da seção 1** e
    pela opção **"Período de análise"** na seção 11. Ele **não** altera o
    gráfico mensal da seção 6, que é sempre do ano inteiro.
- **Remover EPW**: apaga os dados climáticos do documento, voltando a usar
  o **"céu limpo teórico"** (sem nuvens) nos cálculos de radiação. A
  dica abaixo do botão avisa quando este é o caso.

### O que você vê na tela

- **Estação**: nome da cidade e código WMO da estação meteorológica.
- **Lat / Lon / Fuso / Elevação**: dados geográficos da estação.
- **Horas**: o total de horas no período selecionado (8760 é o ano
  inteiro).
- **T média / HR média / Vento médio**: estatísticas do período.
- **Calmas**: porcentagem de horas em que o vento é menor que 0,5 m/s.
- **Dominantes**: os três setores de vento que mais sopram no período,
  ignorando setores vizinhos — para não repetir "Leste" e
  "Leste-Nordeste" como se fossem coisas diferentes.

### Exemplo de uso

Você quer saber se o terreno em Belo Horizonte é quente no verão:
1. Carregue o EPW de Belo Horizonte.
2. Ajuste o período para *Dezembro a Fevereiro*.
3. Observe **T média** e **T máx**.
4. Se quiser cruzar com o mapa de radiação, o mesmo período pode ser
   escolhido na seção 11 em *Período = "Período de análise"*.

---

## 2 · ◉ Localização

Esta seção define o **datum** do projeto — o ponto zero no planeta Terra.
Tudo o que envolve sol, sombras e mapas depende dessa âncora.

### O que os botões fazem

- **Buscar endereço ou colar «lat, lon»**: digite "Av. Paulista, São
  Paulo" ou cole coordenadas como `-23.561, -46.655`. O plugin usa o
  geocodificador do IngeTrazo para encontrar o local.
- **Escolher no mapa…**: abre o seletor visual do IngeTrazo; clique no
  mapa-múndi e escolha o ponto exato.
- **Latitude / Longitude / Aplicar coordenadas**: ajuste manual das
  coordenadas decimais.
- **Fuso horário**: fixe o fuso (ex: `UTC-03:00`) ou deixe em
  `Automática (por longitude)`.
- **Nome**: rótulo livre (ex: "Terreno Alphaville"), aparece na imagem
  exportada e no painel flutuante de informações.

### ⚠️ Aviso sobre mover a origem

Se você já desenhou geometria no modelo e altera a localização para um
ponto muito distante (mais de 1 km), o plugin perguntará se deseja mover
a origem. A geometria **não** se move no espaço físico; ela apenas muda de
endereço global. O eixo (0,0) passa a ser o novo ponto.

### Exemplo de uso

Para comparar dois terrenos em bairros diferentes:
1. Desenhe o primeiro terreno, analise, salve em `.igz`.
2. Em outra cópia do documento, altere a localização para o segundo
   terreno.
3. Compare os resultados.

O aviso de "mover a origem" só aparece se o novo ponto estiver a mais de
1 km do antigo.

---

## 3 · ➤ Norte do projeto

Na maioria dos softwares BIM/CAD, o eixo Y aponta para o "Norte do
desenho". Mas o **Norte geográfico real** (onde o sol nasce e se põe) pode
estar inclinado em relação ao seu desenho.

### O que os botões fazem

- **Perilla (Dial) + Ângulo**: gira o Norte geográfico em relação ao
  modelo. Se você girar para 45°, o sol nascerá a Leste no mundo real, mas
  no seu modelo ele nascerá a Nordeste.
- **0° / −15° / +15°**: ajuste fino.
- **Da aresta selecionada (aponta para o norte)**: existem **duas
  formas** de usar:
  - **Painel**: selecione uma aresta (desenhada sul → norte) no modelo e
    clique no botão. O ângulo é calculado na hora.
  - **Barra (`➤`)**: clique no botão e clique na aresta direto na vista
    3D. O plugin monitora a seleção por ~150 ms e aplica o norte assim
    que houver exatamente uma aresta selecionada. É o caminho mais
    rápido.

> **Nota:** girar o norte **não** gira a geometria do seu prédio. Ele
> apenas gira a incidência solar, o diagrama no céu, as sombras e o mapa
> de fundo.

### Exemplo de uso

Você desenhou um lote com uma rua que corre Norte-Sul. Para garantir que
o plugin entenda isso:
1. Desenhe uma linha do sul para o norte, sobre a rua.
2. Selecione a linha.
3. Clique em **Da aresta selecionada** (painel) **ou** clique no botão
   `➤` da barra e depois na linha (vista 3D).

O norte do diagrama e das sombras fica alinhado com a rua.

---

## 4 · ☀ Data, hora e sombras

Esta seção é o coração da análise solar. A grande sacada é que a data e a
hora **não são só do plugin** — elas são as mesmas usadas pelo painel de
Sombras do próprio IngeTrazo. Mover uma move a outra.

### O que os botões fazem

- **Data / Hora**: sliders que varrem o ano (1 a 365 dias) e o dia (0h às
  24h em passos de 15 min).
- **Equinócios e Solstícios**: atalhos para 21 de março, 21 de junho, 21
  de setembro e 21 de dezembro.
- **▶ Animar trajetória solar**: o sol "anda" pelo céu, as sombras do
  modelo (e do contexto OSM) se movem em tempo real. Você pode parar a
  qualquer momento, pelo painel ou pela barra.
- **Projetar sombras (sol real)**: liga/desliga as sombras reais geradas
  pelo motor do IngeTrazo para a data/hora atual.
- **Escuridão**: controla a intensidade da sombra no chão (0 % a 100 %).
- **Informação do sol**: mostra a altitude e o azimute, o nascer e o pôr
  do sol, o total de horas de sol (ex: 12,1 h) e a temperatura, umidade e
  vento **naquele exato momento** (lidos do EPW).

### Diagrama solar 3D (subseção)

- **Mostrar diagrama solar**: liga/desliga o "domus" (a cúpula do céu).
- **Raio do diagrama**: define o tamanho da cúpula. **Este é o
  multiplicador indireto do tamanho da bússola, dos anéis e da rosa 3D**,
  porque todos usam esse raio como base.
- **Centro (X, Y, Z)**: onde a cúpula está ancorada no modelo (geralmente
  0,0,0). **Escolher centro…** permite escolher outro ponto clicando na
  tela.
- **Trajetórias (dias 21)**: desenha no céu o caminho do sol nos dias 21
  de cada mês selecionado.
- **Banda anual**: desenha a faixa do céu entre o solstício de verão e o
  de inverno.
- **Analemas**: desenha o "oito" que o sol faz se você fotografá-lo todos
  os dias no mesmo horário.
- **Raio solar**: uma linha reta do sol até o centro da cúpula.

### Exemplo de uso

Você quer garantir que a fachada oeste do seu prédio não receba sol no
verão:
1. Escolha 21 de dezembro (solstício de verão no hemisfério sul).
2. Posicione a hora em 15h30.
3. Ative **Projetar sombras (sol real)**.
4. Observe a sombra que cai na fachada oeste.
5. Se quiser ver a evolução do dia, clique em **▶ Animar trajetória
   solar**.

---

## 5 · ≋ Ventos

Esta seção gera o **Gráfico de Rosa dos Ventos** e permite colocar setas
de vento na cena 3D.

### O que você vê

- **Rosa dos ventos (gráfico 2D)**: gráfico polar a partir do EPW. Os
  setores mostram de onde o vento vem (Norte, Nordeste, etc.) e as fatias
  de cor mostram a velocidade (do azul claro ao azul escuro). O "Calmas"
  no topo mostra a porcentagem de dias sem vento.

### O que os controles fazem

- **Cores**: paletas (Âmbar, Azul, Turquesa, etc.). A paleta
  "Personalizada" permite escolher duas cores para o degradê de
  velocidade.
- **3D ground wind rose**: desenha a rosa "deitada" no chão do modelo 3D.
- **Flecha do vento horário**: desenha uma única seta azul na cena,
  indicando o vento do exato momento da seção 4.
- **Flechas de vento**: desenha as setas com base na tabela abaixo.
- **Animar fluxo**: faz as fitas das setas pulsarem, simulando o vento
  soprando.
- **Tabela de direções**: permite criar ventos manualmente. Cada linha
  tem:
  - *Label*: nome (ex: Vento Sul).
  - *Dir°*: direção (0° é Norte, 90° é Leste, 180° é Sul).
  - *m/s*: velocidade.
  - *Cor*: cor da seta.
- **Aplicar ventos dominantes (EPW)**: substitui a tabela manual pelos 3
  ventos mais fortes detectados no EPW (também disponível na barra, no
  botão `◑`).

### Exemplo de uso

Você quer justificar a orientação de uma torre de ventilação natural:
1. Carregue um EPW.
2. Ajuste o período na seção 1 para o verão.
3. A seção 5 mostrará os ventos dominantes de verão.
4. Clique em **Aplicar ventos dominantes (EPW)** para que as setas 3D
   mostrem esses ventos.
5. **Exporte a imagem** com as setas visíveis para justificar a decisão
   em projeto.

---

## 6 · ☵ Dados climáticos

Esta seção oferece uma **visualização gráfica do clima**.

### O que você vê

- **Temperatura (°C)**: um gráfico de linhas que mostra a temperatura
  média (linha laranja), a máxima (topo da barra) e a mínima (base da
  barra) para cada mês do ano. Ajuda a entender a amplitude térmica do
  local.
- **Umidade relativa (%)**: barras azuis com a média mês a mês.
- **Salvar gráficos (PNG)…**: exporta esses dois gráficos **e a rosa dos
  ventos** da seção 5 para um arquivo de imagem. O diálogo abre em
  **Documentos** com o nome sugerido `climate.png`.

### Exemplo de uso

Para inserir o gráfico de clima em uma prancha A3:
1. Carregue o EPW.
2. Clique em **Salvar gráficos (PNG)…**.
3. Escolha o nome e o local (padrão: `Documentos/climate.png`).
4. Serão gerados `climate_rose.png` e `climate_months.png`.
5. Insira os dois arquivos na prancha.

---

## 7 · ▦ Mapa base e contexto

Esta seção tem duas partes: configurar a **imagem de satélite/mapa** por
baixo do modelo, e carregar a **maquete 3D** dos prédios e ruas ao redor
do terreno.

### Mapa base (IngeTrazo)

O mapa base é uma imagem 2D que fica no chão (plano Z=0) para dar contexto
visual de onde você está desenhando.

- **Cartografia**: imagens de satélite (Esri), mapas de ruas
  (OpenStreetMap) ou mapas escuros/claros.
- **URL**: caso escolha "Personalizada", cole o endereço de um servidor
  de mapas (deve conter `{z}`, `{x}`, `{y}`).
- **Extensão e Zoom**: define o tamanho do quadrado do mapa e o nível de
  aproximação.
- **Baixar mapa base**: faz o download.
- **Mostrar mapa / Opacidade**: liga/desliga o mapa e deixa ele
  semi-transparente para o modelo aparecer por cima.

> **Atenção:** o mapa base é uma camada do **próprio IngeTrazo** — o plugin
> só ajusta os parâmetros. Ele também aparece na aba **Terreno**, junto
> com o terreno 3D.

### Edificações de contexto (OSM)

Aqui você baixa os prédios reais do entorno do seu terreno, direto do
OpenStreetMap.

- **Raio e Altura padrão**: o plugin busca prédios num raio de X metros.
  Se um prédio não tiver altura registrada no OSM, usa a "Altura padrão".
- **Apoiar no terreno 3D**: se você estiver usando um modelo de terreno
  (topografia), o prédio do OSM "senta" na cota mais baixa do terreno sob
  ele, em vez de flutuar.
- **Carregar edificações 3D**: baixa os dados em segundo plano, sem
  travar o IngeTrazo.
- **Mostrar edificações**: liga/desliga a maquete cinza dos prédios ao
  redor.
- **Cor / Opacidade / Escala de altura**: muda a aparência dos prédios
  (ex: translúcidos e mais altos, para entender a densidade).
- **Editar edificações**: se ativado, clicar num prédio cinza na vista
  abre o painel "Edifício", permitindo alterar altura, base ou escondê-lo
  individualmente.
- **Remover contexto**: apaga o grupo OSM do documento (um passo de
  desfazer).

### Exemplo de uso

Para analisar o sombreamento causado pela vizinhança:
1. Vá à seção 7, ajuste o **raio** para 300 m.
2. Clique em **Carregar edificações 3D**.
3. Aguarde o download (aparece uma mensagem em "Baixando do
   OpenStreetMap…").
4. Quando terminar, a maquete cinza aparece.
5. Vá à seção 11 e rode o estudo de sombras.

---

## 8 · ⬛ Massas e lotes

As "Massas" e "Lotes" são as ferramentas de **modelagem paramétrica** do
plugin. Servem para criar o volume do prédio (ou do terreno) de forma
simples e extrair áreas automaticamente.

### A diferença entre eles

- **Lote (▬)**: uma **área plana**. Representa o terreno. Sem volume.
- **Massa (⬛)**: um **volume (prisma)**. Representa o prédio, torre ou
  bloco.

### Como usar

1. Desenhe uma face (retângulo, polígono) no chão do IngeTrazo.
2. Selecione a face.
3. Clique em **⬛ Massa da seleção** ou **▬ Lote da seleção**.

O plugin converte a face num objeto paramétrico, apaga a face original e
o coloca numa camada específica ("Massas" ou "Lotes").

### Edição (o que você vê no painel)

Ao selecionar uma massa ou lote na lista, você pode alterar:

- **Nome**: nome do objeto.
- **Tipo**: pode transformar um lote em massa (dar altura) ou vice-versa.
- **Altura**: altura do volume (ex: 12 m).
- **Pisos**: se você define a altura de piso (ex: 3,2 m), o plugin calcula
  quantos andares cabem (ex: 3 pisos).
- **Cota base**: se o terreno for inclinado, você pode levantar o prédio
  do chão.
- **Área em planta / Perímetro**: calculados automaticamente pelo
  contorno.
- **Área construída (GFA)**: área em planta × quantidade de pisos.
- **Volume**: área × altura.
- **Ações**: girar em 15°, duplicar, selecionar ou excluir.

### O resumo urbanístico (importante)

No final da seção, o plugin mostra o **Resumo Urbanístico**. Se você
tiver um Lote e Massas dentro dele, o plugin calcula automaticamente:

- **Índice de Ocupação (IOS)**: a área que os prédios ocupam no lote
  (projeção) ÷ área do lote. Ex: 400 m² de prédio ÷ 1000 m² de lote =
  0.4.
- **Índice de Construção (ICA)**: a área total construída (todos os
  andares) ÷ área do lote. Ex: 3 andares de 400 m² = 1200 m² ÷ 1000 m²
  de lote = 1.2.

### Exemplo de uso

Para testar uma envolvente em um terreno de 1000 m²:
1. Desenhe o terreno, selecione e clique em **Lote da seleção**.
2. Desenhe a planta do prédio, selecione e clique em **Massa da
   seleção**.
3. Defina altura = 9 m (3 pisos de 3 m).
4. O resumo mostra IOS e ICA calculados.
5. Duplique a massa para comparar dois cenários.

> **Dica:** as massas **não** são "blocos rígidos". Se você mover, girar
> ou empurrar com as ferramentas do IngeTrazo, o plugin **relê** a forma
> atual e atualiza os números.

---

## 9 · ⌖ Anotações

Ferramenta para colocar **marcadores (pins) com ícones** sobre o modelo
3D — útil para pranchas e apresentações.

### Como usar

- **Buscar ícone**: filtra a lista (árvore, hospital, ônibus, café, etc.).
- **⌖ Ponto**: ferramenta de clique na vista. Clique e o pin é criado. O
  modo é contínuo (vários cliques seguidos). Pressione **Esc** para
  sair.
- **★ Com o ícone selecionado**: cria o pin com o ícone escolhido na
  lista.
- **Lista de anotações**: mostra todos os pins criados.

### Personalização

- **Texto**: muda a etiqueta (ex: "Ponto 1" → "Entrada Principal").
- **Usar ícone selecionado / Remover ícone / Eliminar**: ações do pin.
- **Estilo das anotações**:
  - **Cores**: cor do ícone, do texto e da linha-guia.
  - **Fundo circular**: bolinha com fundo escuro atrás do ícone.
  - **Tamanho e altura**: quão grande é o pin e a altura em que ele
    flutua.
  - **Linha-guia**: linha do pin até o chão (útil para marcar o solo).
- **Aplicar estilo a todas**: se você mudou a cor e quer que todos os
  pins fiquem iguais.

### Exemplo de uso

Para uma prancha de análise de fluxos:
1. Coloque pins nos pontos de entrada, saídas de emergência, pontos de
   ônibus, comércios próximos.
2. Use o ícone **🚌** para paradas, **🍴** para restaurantes.
3. Aplique o estilo "fundo circular" para que fiquem visíveis em qualquer
   imagem de fundo.

---

## 10 · ◐ Visualização

Aqui você controla o "cenário" da análise 3D (o **Domus**) e escolhe
posições de câmera rápidas.

### O que os controles fazem

- **Mostrar a análise na vista**: botão mestre. Se desmarcado, o plugin
  esconde **tudo** o que ele desenha sobre o modelo (sol, diagrama,
  bússola, anéis, pins, setas). O modelo do IngeTrazo continua na tela.
  Útil para tirar prints limpos do prédio.
- **Bússola e graus**: liga/desliga o anel graduado.
- **Anéis**: desenha círculos concêntricos (como um alvo) a partir do
  centro do modelo, para você ter noção de distância e escala (ex: 4
  anéis, a cada 25 m).
- **Escala de etiquetas**: aumenta ou diminui o tamanho do texto de tudo
  (horas do sol, texto dos pins, bússola).
- **Convenções**: uma legenda dinâmica; mostra qual símbolo representa
  cada coisa que está na tela.

### Vistas rápidas (câmeras)

Em vez de usar o mouse para navegar, clique em:

- **Planta**: câmera de cima.
- **Iso SE/SO/NE/NO**: vistas isométricas (perspectiva "aérea" de 4
  cantos).
- **Aérea**: uma vista em perspectiva mais natural.
- **Do sol**: a câmera se posiciona exatamente no sol, olhando para o
  chão. Mostra a sombra do momento da seção 4.
- **Enquadrar**: ajusta a câmera para caber tudo na tela.
- **Persp./Paral.**: alterna entre perspectiva realista (com ponto de
  fuga) e projeção paralela (isométrica).

### Exemplo de uso

Para uma prancha de apresentação:
1. Desmarque **Mostrar a análise na vista** para esconder o domus.
2. Use a vista **Aérea**.
3. Marque **Mostrar a análise na vista** de novo só com a bússola e os
   anéis (desmarcando o diagrama solar).
4. Exporte em 4K.

---

## 11 · ☀ Radiação solar e sombras

Esta é a seção mais "pesada" do plugin. Calcula a física de como o sol e
a sombra interagem com o modelo. O resultado é um **mapa de cores
pintado sobre as superfícies** do modelo 3D.

### Configuração comum (topo da seção)

- **Superfícies**: o que analisar?
  - *Todo o modelo*: tudo o que estiver visível na tela (exceto o OSM,
    para não pesar).
  - *Massas e lotes*: apenas os prédios que você criou.
  - *Seleção*: apenas os objetos selecionados.
  - *Só o solo*: para ver a mancha de sombra no chão.
- **Resolução**:
  - *Por superfície*: pinta a face inteira de uma cor só (rápido).
  - *Malha de 2 m / 1 m / 0.5 m*: divide a face em quadradinhos para um
    degradê suave (mais lento, ideal para fachadas).
- **Solo ao redor**: desenha um chão virtual para capturar as sombras de
  todo o terreno.

### Estudo 1 — Radiação solar incidente (energia)

Calcula quanta energia solar (em kWh/m²) bate em cada superfície.

1. **Período**: dia atual, um mês, o período de análise (definido na
   seção 1) ou o ano todo.
2. **Albedo**: reflete a cor do chão (0 = preto que absorve tudo, 0.9 =
   neve que reflete tudo).
3. **☀ Calcular radiação**: faz o cálculo.
   - *O que ele faz*: dispara milhares de raios do sol contra o modelo.
     Se bater na parede, soma pontos. Se bater no contexto OSM, faz
     sombra. Calcula a **difusa** do céu (usando as 145 direções de
     Tregenza) e a **reflexão** do chão (albedo).
   - Sem EPW carregado, usa-se um **céu limpo teórico** (máximos
     possíveis). O rodapé da seção avisa.
4. **Resultado**: o modelo é pintado com uma escala de cores (geralmente
   azul = frio / pouco sol, amarelo = muito sol).
5. **Painel flutuante da escala**: aparece arrastável em cima da tela.
   Pode ser reposicionado com o mouse.

### Estudo 2 — Estudo de sombras (horas)

Calcula por quanto tempo uma superfície fica na sombra.

1. **De / Até / Intervalo**: define a janela (ex: 7h às 18h, de 30 em 30
   min).
2. **◑ Calcular estudo de sombras**: faz o cálculo.
3. **Resultado**: o modelo é pintado em tons de cinza. Branco = sol o dia
   inteiro. Preto = sombra o tempo todo.
4. **Mostrar**: *Horas de sombra* ou *Horas de sol (insolação)*. As cores
   ficam por ponto ao alternar; só os rótulos mudam.

### A escala flutuante (painel arrastável)

Sempre que um cálculo termina, um painel aparece sobre a tela mostrando a
legenda de cores (de quanto a quanto vai a escala).

- Você pode alterar as cores (Ecotect, Cinzas, Térmica) e a escala **no
  próprio painel**.
- O painel pode ser **arrastado** para qualquer canto da tela.
- Você pode remover o resultado a qualquer momento (é um passo de
  desfazer).

### Exemplo de uso — radiação anual

Para justificar brises e sombreamento:
1. Seção 11, *Período = "Ano completo"*.
2. Clique em **Calcular radiação**.
3. A fachada oeste ficará vermelha/amarela; a leste, azul.
4. **Exporte a imagem** com o painel de escala visível.

### Exemplo de uso — sombra de inverno

Para verificar se a sala de aula recebe sol no inverno:
1. Seção 4, data = 21 de junho.
2. Seção 11, *De 8h a 16h*, intervalo de 30 min.
3. *Mostrar = "Horas de sol (insolação)"*.
4. Clique em **Calcular estudo de sombras**.
5. O piso da sala aparece branco se recebe sol o dia inteiro.

---

## 12 · ⇩ Exportar imagem

Transforma a tela 3D em uma imagem de alta qualidade para relatórios.

- **Resolução**: FHD (1920 px), 2K (2560 px), 4K (3840 px) ou 5K
  (5120 px).
- **Exportar imagem (PNG)…**: salva a imagem. O diálogo abre em
  **Documentos** com o nome sugerido `<nome_do_sítio>_analysis.png` (ou
  `site_analysis.png`).
- **O que vai na imagem**: tudo o que você está vendo na tela (modelo
  3D, sombras do IngeTrazo) **+** tudo o que o plugin desenhou por cima
  (diagrama solar, bússola, pins, mapa de radiação, escala de cores).
  Os dois painéis flutuantes também aparecem, na posição em que
  estiverem.
- **Painel de informações**:
  - **Título do painel**: nome que aparece no cartão.
  - **Posição**: canto superior/inferior, esquerda/direita.
  - **Mostrar painel flutuante…**: desenha um quadro escuro no canto da
    imagem listando data, hora, localização, dados do sol e do clima
    naquele momento. Útil para compor pranchas sem digitar legendas.

### Exemplo de uso

Para uma prancha A2 em 300 dpi:
1. Componha a vista com a câmera desejada.
2. Escolha **4K (3840 px)**.
3. Marque **Mostrar painel flutuante**.
4. Escolha a posição do painel (ex: canto superior direito).
5. Clique em **Exportar imagem (PNG)…**.
6. No seu editor de imagem, posicione as demais anotações por cima.

---

## Tabela de atalhos (barra de ferramentas)

Todos os atalhos usam `Qt.WindowShortcut` — só disparam quando a janela
do IngeTrazo está em foco. Podem ser alterados em `tools/toolbar.py`.

| Seção | Atalho | Ação |
|---|---|---|
| 1  | `Shift+Y`     | Abrir EPW… |
| 2  | `Shift+K`     | Escolher localização no mapa… |
| 3  | `Shift+C`     | Definir norte da aresta |
| 4  | `Shift+H`     | Mostrar / ocultar a análise |
| 4  | `Shift+Space` | Animar a trajetória solar |
| 5  | `Shift+W`     | Aplicar ventos dominantes (EPW) |
| 6  | `Shift+G`     | Salvar gráficos do clima (PNG)… |
| 7  | `Shift+B`     | Baixar mapa base |
| 7  | `Shift+O`     | Carregar edificações do OSM |
| 7  | `Shift+Delete`| Remover contexto OSM |
| 8  | `Shift+M`     | Massa a partir das faces |
| 8  | `Shift+L`     | Lote a partir das faces |
| 9  | `Shift+A`     | Anotar com o ícone selecionado |
| 10 | `Shift+5`     | Vista em planta |
| 10 | `Shift+0`     | Enquadrar o sítio |
| 11 | `Shift+R`     | Calcular radiação |
| 12 | `Shift+E`     | Exportar PNG… |
| 12 | `Shift+I`     | Mostrar / ocultar painel de informação |
| —  | `Shift+P`     | Mostrar / ocultar o painel de análise |

---

## Painéis flutuantes arrastáveis

O plugin desenha **dois painéis flutuantes** sobre a vista 3D, ambos
podendo ser **arrastados com o mouse** para qualquer canto da tela:

- **Análise de Sítio** — ativado na seção 12. Mostra sítio, data, hora,
  sol, clima na hora atual, uma legenda viva do que está visível e a
  média climática do período de análise.
- **Radiação / Sombras** — ativado na seção 11. Só aparece quando há um
  mapa visível **e** a caixa correspondente marcada.

Ambos saem na **imagem exportada**, na posição em que estiverem.

---

## Onde os diálogos começam

Para não abrir na pasta de instalação do IngeTrazo, os diálogos de
arquivo começam em pastas do usuário:

- **Abrir EPW…** → pasta **Downloads**.
- **Salvar gráficos (PNG)…** → pasta **Documentos**, nome sugerido
  `climate.png`.
- **Exportar imagem (PNG)…** → pasta **Documentos**, nome sugerido
  `<nome_do_sítio>_analysis.png`.

Você pode navegar para outra pasta dentro do diálogo normalmente.

---

*Fim do manual.*
```
