📷 CadVision - Sistema de Cadastro Inteligente
Sistema avançado de cadastro de produtos que utiliza visão computacional (Google Cloud Vision) e uma API de dados fiscais (Cosmos Bluesoft) para automatizar a identificação de produtos a partir de imagens.

📜 Sobre o Projeto
O CadVision foi criado para resolver o problema tedioso e propenso a erros do cadastro manual de produtos. Através de uma interface web moderna, o usuário pode enviar a foto de um produto e o sistema, utilizando um pipeline de inteligência artificial, extrai, valida e enriquece os dados, entregando um cadastro completo e confiável.

O projeto foi arquitetado pensando em escalabilidade, com uma clara separação entre o backend (API REST) e o frontend, preparando o terreno para uma futura solução SaaS.

(Aqui você pode adicionar um GIF ou uma captura de tela do sistema em ação)
![Demo do CadVision](link_para_sua_imagem_ou_gif.gif)

✨ Funcionalidades Principais
Extração Inteligente por Imagem: Utiliza a API Google Cloud Vision para OCR e detecção de logos.

Validação e Enriquecimento de Dados: Integra-se com a API do Cosmos Bluesoft para obter dados fiscais e de produto precisos a partir do GTIN (código de barras).

Cache Inteligente: Armazena os resultados de consultas externas em um banco de dados local para otimizar a velocidade e reduzir custos.

Pré-processamento de Imagem: Usa OpenCV para aprimorar a qualidade das imagens antes da análise, aumentando a precisão do OCR.

API RESTful Completa: Backend robusto construído com FastAPI, com documentação interativa automática.

Interface Web Responsiva: Frontend limpo e funcional construído com HTML, CSS e JavaScript puros.

🛠️ Tecnologias Utilizadas
Categoria	Tecnologia
Backend	Python 3.8+, FastAPI, Uvicorn
Visão Computacional	Google Cloud Vision API, OpenCV
API Externa	Cosmos Bluesoft API
Banco de Dados	SQLite (com plano de migração para PostgreSQL)
Frontend	HTML5, CSS3, JavaScript (Vanilla)
Dependências	Requests, python-dotenv, Pydantic

Exportar para as Planilhas
🚀 Começando
Siga os passos abaixo para configurar e rodar o projeto em seu ambiente local.

Pré-requisitos
Python 3.8+

Git

Uma conta e chave de API do Google Cloud Vision.

Uma conta e chave de API do Cosmos Bluesoft.

Guia de Instalação
Clone o repositório:

Bash

git clone https://github.com/seu-usuario/cadvision.git
cd cadvision
Navegue para a pasta do backend:

Bash

cd backend
Crie e ative um ambiente virtual:

Bash

# Criar o ambiente
python -m venv venv

# Ativar no Windows (PowerShell)
.\venv\Scripts\Activate.ps1

# Ativar no Mac/Linux
# source venv/bin/activate
Instale as dependências do Python:

Bash

pip install -r requirements.txt
Configure suas chaves de API:

Na pasta backend/, crie um arquivo chamado .env.

Copie o conteúdo do arquivo .env.example (se você criar um) ou adicione as seguintes variáveis:

# Arquivo: backend/.env
COSMOS_API_KEY="SUA_CHAVE_DO_COSMOS_AQUI"
Coloque seu arquivo de chave do Google Cloud na pasta backend/keys/ com o nome vision.json.

Executando a Aplicação
Inicie o servidor backend:

Certifique-se de que você está na pasta backend/ com o venv ativado.

Bash

uvicorn main:app --reload
Acesse a aplicação:

Abra seu navegador e acesse: http://127.0.0.1:8000

Explore a API:

A documentação interativa da API está disponível em: http://127.0.0.1:8000/docs

🏗️ Estrutura do Projeto
O projeto é organizado em duas partes principais para uma clara separação de responsabilidades:

/frontend: Contém todos os arquivos da interface do usuário (HTML, CSS, JavaScript, imagens e outros assets).

/backend: Contém a aplicação FastAPI, seguindo uma arquitetura de serviços:

/app/core: Configurações centrais.

/app/services: Toda a lógica de negócio (comunicação com APIs, análise de dados).

/app/models: Modelos de dados Pydantic.

/app/database.py: Gerenciamento da conexão com o banco de dados.

main.py: Ponto de entrada da API, responsável por definir as rotas.

🗺️ Roadmap
[ ] Migrar o banco de dados de SQLite para Cloud SQL (PostgreSQL).

[ ] Containerizar a aplicação com Docker.

[ ] Fazer o deploy para um ambiente de produção usando Google Cloud Run.

[ ] Implementar autenticação de usuários.

📄 Licença
Este projeto está sob a licença MIT. Veja o arquivo LICENSE para mais detalhes.