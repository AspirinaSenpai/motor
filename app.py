# app.py
from flask import Flask, render_template, request, redirect, url_for, send_file, flash, jsonify
from werkzeug.utils import secure_filename
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from google.oauth2.service_account import Credentials
import gspread
import google.generativeai as genai
from fpdf import FPDF
import os
import datetime
import PyPDF2
import docx
import tempfile
import uuid
from io import BytesIO

app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_aqui'  # Altere para uma chave segura em produção

# Configurações
UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), 'motor_reports')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

ALLOWED_EXTENSIONS = {'pdf', 'docx'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

class PDFRelatorio(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=15)
        self.add_page()
        self.set_left_margin(15)
        self.set_right_margin(15)
        self.set_font("Helvetica", size=12)

    def header(self):
        self.set_font("Helvetica", 'B', 14)
        self.cell(0, 10, "Relatório Técnico do Motor", ln=True, align='C')
        self.set_font("Helvetica", '', 10)
        data = datetime.datetime.now().strftime("Data da Análise: %d/%m/%Y - %H:%M")
        self.cell(0, 10, data, ln=True, align='C')
        self.ln(5)

    def add_relatorio(self, texto):
        texto = self.limpar_caracteres_especiais(texto)
        for linha in texto.split("\n"):
            linha = linha.strip()
            if linha:
                self.multi_cell(0, 8, linha)
                self.ln(1)

    def limpar_caracteres_especiais(self, texto):
        # Substitui caracteres problemáticos mantendo Ω e outros símbolos técnicos
        substituicoes = {
            '–': '-', '—': '-', '´': "'", '“': '"', '”': '"', 
            '‘': "'", '’': "'", '…': '...', '®': '(R)', 
            '©': '(C)', '™': '(TM)'
        }
        for orig, sub in substituicoes.items():
            texto = texto.replace(orig, sub)
        
        # Mantém Ω e outros símbolos técnicos
        try:
            return texto.encode('latin-1', 'ignore').decode('latin-1')
        except:
            return texto

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Processar formulário principal
        email_origem = request.form.get('email_origem')
        email_destino = request.form.get('email_destino')
        senha_app = request.form.get('senha_app')
        assunto = request.form.get('assunto', 'Relatório Técnico do Motor - IA')
        modelo_motor = request.form.get('modelo_motor')
        corrente_nominal = request.form.get('corrente_nominal')
        tensao_nominal = request.form.get('tensao_nominal')
        tipo_ligacao = request.form.get('tipo_ligacao')
        observacoes = request.form.get('observacoes', '')
        
        # Verificar qual botão foi pressionado
        if 'gerar_relatorio' in request.form:
            # Validação básica
            if not modelo_motor:
                flash('Por favor, informe o modelo do motor.', 'error')
                return redirect(url_for('index'))
                
            try:
                relatorio = gerar_relatorio_ia(
                    modelo_motor, corrente_nominal, tensao_nominal, 
                    tipo_ligacao, observacoes, request.files.get('manual')
                )
                
                # Criar PDF em memória
                pdf_buffer = BytesIO()
                criar_pdf(relatorio, pdf_buffer)
                pdf_buffer.seek(0)
                
                # Salvar o PDF temporariamente com um ID único
                report_id = str(uuid.uuid4())
                pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], f'report_{report_id}.pdf')
                with open(pdf_path, 'wb') as f:
                    f.write(pdf_buffer.getvalue())
                
                # Retornar o ID do relatório para download
                return jsonify({
                    'status': 'success',
                    'message': 'Relatório gerado com sucesso!',
                    'report_id': report_id
                })
                
            except Exception as e:
                return jsonify({
                    'status': 'error',
                    'message': f'Erro ao gerar relatório: {str(e)}'
                }), 500
                
        elif 'enviar_email' in request.form:
            # Validação de e-mail
            if not email_origem or '@' not in email_origem:
                flash('Por favor, insira um e-mail remetente válido.', 'error')
                return redirect(url_for('index'))
                
            if not email_destino or '@' not in email_destino:
                flash('Por favor, insira um e-mail destinatário válido.', 'error')
                return redirect(url_for('index'))
                
            if not senha_app:
                flash('Por favor, insira a senha do app.', 'error')
                return redirect(url_for('index'))
                
            if not modelo_motor:
                flash('Por favor, informe o modelo do motor.', 'error')
                return redirect(url_for('index'))
                
            try:
                relatorio = gerar_relatorio_ia(
                    modelo_motor, corrente_nominal, tensao_nominal, 
                    tipo_ligacao, observacoes, request.files.get('manual')
                )
                
                # Criar PDF temporário
                temp_pdf = os.path.join(app.config['UPLOAD_FOLDER'], f'temp_{uuid.uuid4()}.pdf')
                criar_pdf(relatorio, temp_pdf)
                
                # Enviar e-mail
                enviar_email(
                    email_origem, email_destino, senha_app, assunto,
                    modelo_motor, observacoes, temp_pdf
                )
                
                # Remover arquivo temporário
                if os.path.exists(temp_pdf):
                    os.remove(temp_pdf)
                
                flash('E-mail enviado com sucesso!', 'success')
                return redirect(url_for('index'))
                
            except Exception as e:
                flash(f'Erro ao enviar e-mail: {str(e)}', 'error')
                return redirect(url_for('index'))
    
    return render_template('index.html')

@app.route('/download/<report_id>')
def download_report(report_id):
    pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], f'report_{report_id}.pdf')
    
    if os.path.exists(pdf_path):
        return send_file(
            pdf_path,
            as_attachment=True,
            download_name=f'relatorio_motor_{report_id[:8]}.pdf',
            mimetype='application/pdf'
        )
    else:
        flash('Relatório não encontrado ou expirado.', 'error')
        return redirect(url_for('index'))

def extrair_texto_manual(arquivo):
    try:
        if arquivo and allowed_file(arquivo.filename):
            filename = secure_filename(arquivo.filename)
            temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            arquivo.save(temp_path)
            
            if filename.lower().endswith('.pdf'):
                with open(temp_path, 'rb') as f:
                    leitor = PyPDF2.PdfReader(f)
                    texto = ""
                    for pagina in leitor.pages:
                        texto += pagina.extract_text()
                    return texto
            
            elif filename.lower().endswith('.docx'):
                doc = docx.Document(temp_path)
                return "\n".join([para.text for para in doc.paragraphs])
            
            # Remover arquivo temporário após leitura
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
        return ""
    except Exception as e:
        print(f"Erro ao extrair texto do manual: {str(e)}")
        return ""

def ler_planilha():
    try:
        SERVICE_ACCOUNT_FILE = os.path.join(os.getcwd(), 'gen-lang-client-0707507427-c275385a009d.json')
        SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
        SPREADSHEET_ID = "1vsWF18ozVUx3B296GtQYXncYHsG6ihhod6ViAKF7bR0"

        # Autenticação
        creds = Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE,
            scopes=SCOPES
        )
        
        # Força a atualização do token
        creds.refresh(Request())
        
        # Acesso à planilha
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_ID).sheet1
        
        # Processamento dos dados
        valores = sheet.get_all_values()
        
        if not valores:
            return {}

        cabecalho = valores[0]
        ult_linha = valores[-1] if len(valores) > 1 else cabecalho
        ultimo_dado = dict(zip(cabecalho, ult_linha))

        # Conversão de valores numéricos
        for chave in ultimo_dado:
            valor = ultimo_dado[chave]
            if isinstance(valor, str) and "," in valor:
                try:
                    ultimo_dado[chave] = float(valor.replace(",", "."))
                except ValueError:
                    pass  # Mantém como string se não puder converter

        return ultimo_dado

    except Exception as e:
        print(f"Erro ao acessar planilha: {str(e)}")
        return {}  # Retorna dicionário vazio em caso de erro

def gerar_relatorio_ia(modelo_motor, corrente_nominal, tensao_nominal, tipo_ligacao, observacoes, manual_file):
    genai.configure(api_key="AIzaSyAza9XWD0-nyO2FRwhWzowIl9e1_k-FJgs")

    ultimo_dado = ler_planilha()
    dados_texto = "\n".join([f"- {k}: {v}" for k, v in ultimo_dado.items()])
    
    info_motor = f"""
INFORMAÇÕES DO MOTOR:
- Modelo: {modelo_motor}
- Corrente Nominal: {corrente_nominal} A
- Tensão Nominal: {tensao_nominal} V
- Tipo de Ligação: {tipo_ligacao}
"""

    manual_texto = ""
    if manual_file and allowed_file(manual_file.filename):
        manual_texto = f"""
MANUAL/FICHA TÉCNICA:
{extrair_texto_manual(manual_file)}
"""

    prompt = f"""
Você é um técnico especialista em manutenção de motores elétricos.

{info_motor}

DADOS COLETADOS DO MOTOR:
{dados_texto}

{manual_texto}

{'OBSERVAÇÕES EXTRAS DO USUÁRIO:\n' + observacoes + '\n\n' if observacoes else ''}

Faça uma análise técnica detalhada considerando todas essas informações.
"""

    model = genai.GenerativeModel("gemini-2.5-pro")
    response = model.generate_content(prompt)
    return response.text

def criar_pdf(relatorio, output):
    try:
        # Converter caracteres especiais antes de criar o PDF
        relatorio = relatorio.encode('latin-1', 'replace').decode('latin-1')
        
        pdf = PDFRelatorio()
        pdf.add_relatorio(relatorio)
        pdf.output(output)
    except Exception as e:
        app.logger.error(f"Erro ao criar PDF: {str(e)}")
        raise

def enviar_email(email_origem, email_destino, senha_app, assunto, modelo_motor, observacoes, pdf_path):
    try:
        # Criar mensagem com codificação UTF-8
        mensagem = MIMEMultipart()
        mensagem["From"] = email_origem
        mensagem["To"] = email_destino
        mensagem["Subject"] = assunto
        mensagem.preamble = 'This is a multi-part message in MIME format.'

        # Corpo do email com codificação UTF-8
        corpo = f"""Relatório Técnico do Motor - {modelo_motor}

Segue em anexo o relatório técnico gerado pelo sistema.

"""
        if observacoes:
            corpo += "\nObservações adicionais:\n" + observacoes

        # Parte 1: texto do email
        part1 = MIMEText(corpo, _charset='utf-8')
        mensagem.attach(part1)

        # Parte 2: anexo PDF
        with open(pdf_path, "rb") as arquivo:
            part2 = MIMEApplication(arquivo.read(), _subtype="pdf")
            part2.add_header('Content-Disposition', 'attachment', 
                           filename=f"relatorio_{modelo_motor}.pdf")
            mensagem.attach(part2)

        # Enviar email
        with smtplib.SMTP("smtp.gmail.com", 587) as servidor:
            servidor.starttls()
            servidor.login(email_origem, senha_app)
            servidor.send_message(mensagem, from_addr=email_origem, to_addrs=email_destino)

    except Exception as e:
        app.logger.error(f"Erro ao enviar email: {str(e)}")
        raise Exception(f"Erro ao enviar e-mail: {str(e)}")

@app.route('/limpar', methods=['POST'])
def limpar_campos():
    return jsonify({'status': 'success', 'message': 'Campos limpos com sucesso!'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
