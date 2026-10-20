# iLoveCaioPDF

Aplicativo para Windows desenvolvido por **Caio Pedro Neto Xavier**, com interface em português para trabalhar com PDFs, documentos Word e imagens.

## Funcionalidades

- Unir PDFs e imagens na ordem da fila. As imagens são convertidas automaticamente em páginas do PDF final.
- Converter imagens em lote, criando um PDF separado para cada arquivo.
- Converter arquivos Word (`.doc` e `.docx`) para PDF usando LibreOffice.
- Dividir PDFs por página, intervalo ou quantidade de páginas.
- Compactar PDFs em três níveis, com Ghostscript e otimização adicional com qpdf quando disponível.
- Arrastar e soltar arquivos, reorganizar a fila e remover todos os itens com **Limpar fila**.
- Exibir as operações de acordo com os tipos de arquivo selecionados.

Imagens aceitas: **JPG, JPEG, PNG, BMP, WEBP, TIF e TIFF**. A conversão respeita a orientação da foto, utiliza fundo branco nas transparências e preserva as páginas dos TIFFs com múltiplas páginas. As imagens podem ser recomprimidas durante a conversão.

## Executar pelo código

Requisitos: **Windows e Python 3.11 ou mais recente**, com suporte a Tkinter.

No PowerShell, dentro da pasta do projeto:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe ilovecaiopdf.py
```

### Ferramentas externas

Estas ferramentas não estão incluídas neste repositório:

| Ferramenta | Uso | Onde obter |
| --- | --- | --- |
| LibreOffice | Converter Word para PDF | https://www.libreoffice.org/download/download-libreoffice/ |
| Ghostscript | Compactar PDFs | https://ghostscript.com/releases/gsdnld.html |
| qpdf | Otimização adicional de PDFs; opcional | https://github.com/qpdf/qpdf/releases |

Para unir PDFs e imagens, converter imagens ou dividir PDFs, LibreOffice e Ghostscript não são necessários.

O aplicativo procura as ferramentas nas pastas comuns de instalação e nas pastas locais `LibreOffice`, `Ghostscript/bin` e `qpdf/bin`. O qpdf também pode estar no PATH. Os caminhos encontrados para LibreOffice e Ghostscript ficam salvos em `config.json`, criado automaticamente ao lado do código ou do executável.

## Gerar o executável

Execute no Windows, usando o ambiente virtual criado acima:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm iLoveCaioPDF.spec
```

O resultado estará em `dist/iLoveCaioPDF.exe`. As bibliotecas Python, o ícone e os recursos da interface são empacotados no executável. LibreOffice, Ghostscript e qpdf continuam sendo ferramentas externas: instale-as ou mantenha as pastas portáteis compatíveis ao lado do executável.

## Operações disponíveis por tipo de fila

| Conteúdo da fila | Operações |
| --- | --- |
| Uma imagem | Converter imagem para PDF |
| Várias imagens | Converter em PDFs separados ou unir em um PDF |
| PDFs e imagens | Unir na ordem escolhida |
| Um PDF | Dividir e compactar |
| Vários PDFs | Unir e compactar |
| Somente Word | Converter Word para PDF |
| Word misturado com outros tipos | Aviso para reorganizar a fila |

Durante o processamento, alterações na fila ficam bloqueadas. Na conversão de imagens, nomes repetidos recebem um número para preservar os PDFs existentes; uma imagem com erro é informada e as demais continuam sendo processadas.

## Observações

- O nível potente de compactação pode selecionar um resultado em tons de cinza para documentos classificados como predominantemente sem texto.
- A conversão Word ainda não tem a mesma proteção contra nomes repetidos da conversão de imagens. Evite enviar documentos Word de mesmo nome para a mesma pasta de destino.
- Os testes anteriores incluíram união mista, conversão de 100 JPGs pequenos, rotação, transparência, TIFFs com várias páginas e opções da interface. O tempo depende do tamanho e da quantidade de arquivos; isso não representa uma validação de milhares de documentos grandes.
- Os arquivos são processados localmente pelas bibliotecas e ferramentas instaladas.

## Arquivos principais

- `ilovecaiopdf.py`: interface e processamento.
- `iLoveCaioPDF.spec`: configuração de empacotamento do PyInstaller.
- `icone.ico`: ícone do aplicativo.
- `requirements.txt`: dependências para executar.
- `requirements-build.txt`: dependências adicionais para gerar o executável.

As pastas de compilação, executáveis, ferramentas externas, cópias de segurança e configurações pessoais ficam fora do controle de versão.
