# 🌟 Tutorial Passo a Passo para utilizar o python e github

Olá! Que ótimo que você quer começar a explorar o mundo da programação! Vou guiá-lo(a) de forma simples e amigável por todo o processo. Não se preocupe se algo parecer complicado no início - vamos desbravar juntos! 😊

---

## 🐍 **PASSO 1: Instalando o Python**

### *(Precisamos do Python para executar códigos)*

1️⃣ **Acesse o site oficial**:  
Abra seu navegador e vá para [python.org](https://www.python.org/)

2️⃣ **Faça o download**:  

- Clique em "Downloads" > "Python 3.12.x" (ou a versão mais recente)
- ⚠️ **IMPORTANTE**: Marque ✅ **"Add Python to PATH"** durante a instalação!

3️⃣ **Siga o instalador**:  

- Clique em "Install Now"
- Quando finalizar, clique em "Close"

4️⃣ **Verifique se funcionou**:  

- Abra o **Prompt de Comando** (Windows: `Win + R` > digite `cmd` > Enter)
- Digite:

  ```bash
  python --version
  ```

- Se aparecer `Python 3.12.x` (ou similar), **sucesso!** 🎉

> 💡 **Dica**: Se não funcionar, reinicie seu computador e tente novamente.

---

## 📥 **PASSO 2: Baixando o Repositório do GitHub**

#### *(Duas opções - escolha a que preferir)*

### **Opção A: Baixar ZIP (mais fácil)**

1️⃣ Vá até o repositório no GitHub (ex: `https://github.com/LAMP-LUCAS/AutoSINAPI`)  
2️⃣ Clique no botão verde "Code" > "Download ZIP"  
3️⃣ Extraia o ZIP em uma pasta de sua preferência (ex: `Documentos/AutoSINAPI`)

### **Opção B: Instalar Git + Clonar (recomendado para atualizações)**

1️⃣ **Instale o Git**:  

- Baixe em [git-scm.com](https://git-scm.com/)  
- Siga a instalação com opções padrão

2️⃣ **Clone o repositório**:  

- Abra o Prompt de Comando
- Navegue até sua pasta de projetos:

     ```bash
     cd Documentos
     ```

  - Cole o comando de clone (encontrado no botão "Code" do GitHub):

     ```bash
     git clone https://github.com/LAMP-LUCAS/AutoSINAPI.git
     ```

---

## ⚙️ **PASSO 3: Instalando os Requirements**

### *(São as bibliotecas que o projeto precisa)*

1️⃣ **Abra o Prompt na pasta do projeto**:  

- Digite `cmd` na barra de endereço do explorador de arquivos (dentro da pasta do projeto)  
   *(ou use `cd` para navegar até ela)*

2️⃣ **Instale os pacotes**:  
Digite este comando mágico ✨:

```bash
pip install -r requirements.txt
```

> ⚠️ **Se encontrar erros**:  
>
> - Tente `pip3 install -r requirements.txt`  
> - Ou `python -m pip install -r requirements.txt`

---

## 🚀 **PASSO 4: Executando o Projeto**

1️⃣ **Descubra como iniciar**:  

- Verifique o arquivo `README.md` (geralmente tem instruções)  
- Procure por arquivos como `main.py`, `app.py` ou `start.py` no nosso caso é: `autosinapi_pipeline.py`

2️⃣ **Execute pelo Prompt**:  
Na mesma pasta do projeto:

```bash
python nome_do_arquivo.py
```

Exemplo:

```bash
python tools/autosinapi_pipeline.py
```

3️⃣ **Se precisar de ajuda**:  

- Projetos complexos podem ter um `setup.py` ou scripts específicos  
- Não hesite em consultar o README ou perguntar ao criador do repositório!

---

## 💡 **Dicas Importantes para o Caminho**

- **Erros são normais!** Eles são professores disfarçados 😉  
- **Ambientes virtuais** (virutalenv) são úteis para projetos complexos  
- Sempre **atualize o pip** antes de instalar requirements:

  ```bash
  python -m pip install --upgrade pip
  ```

- Se precisar de ajuda extra, comunidades como **Stack Overflow** são ótimas, mas temos a nossa comunidade veja mais no [FOTON](https://github.com/LAMP-LUCAS/foton)!

---

✨ **Parabéns!** Você acabou de dar um passo gigante no mundo da programação.  
Lembre-se: cada expert um dia foi iniciante. Continue explorando, e se encontrar dificuldades, respire fundo e tente novamente. Você consegue! 💪

> "A jornada de mil milhas começa com um único passo" - Lao Tzu  
> Seu passo foi dado hoje! 🎉

Este tutorial foi feito com carinho para você, dê uma estrelinha em nosso repositório e não demore a mandar uma sugestõão de melhorias ou relatar os erros em uma issue alí no botão acima! Qualquer dúvida, estou à disposição. 😊
