import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
from fpdf import FPDF
import base64
import datetime

class PDFRelatorio(FPDF):
    def __init__(self):
        super().__init__()
        self.add_page()
        self.set_font("Arial", size=12)

    def adicionar_texto(self, texto):
        self.multi_cell(0, 10, texto)

    def salvar(self, caminho):
        self.output(caminho)

def enviar_email(destinatario, assunto, corpo, caminho_anexo=None):
    api_key = os.environ.get("SENDGRID_API_KEY")
    if not api_key:
        print("Erro: SENDGRID_API_KEY não definida.")
        return

    mensagem = Mail(
        from_email='seu_email_verificado@seudominio.com',
        to_emails=destinatario,
        subject=assunto,
        html_content=corpo
    )

    if caminho_anexo:
        try:
            with open(caminho_anexo, 'rb') as f:
                data = f.read()
                f_encoded = base64.b64encode(data).decode()

            anexo = Attachment(
                FileContent(f_encoded),
                FileName(os.path.basename(caminho_anexo)),
                FileType("application/pdf"),
                Disposition("attachment")
            )
            mensagem.attachment = anexo
        except Exception as e:
            print(f"Erro ao anexar arquivo: {e}")
            return

    try:
        sg = SendGridAPIClient(api_key)
        resposta = sg.send(mensagem)
        print(f"E-mail enviado! Status: {resposta.status_code}")
    except Exception as e:
        print(f"Erro no envio do e-mail: {e}")

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Gerador de Relatório")
        self.geometry("400x300")

        ttk.Label(self, text="Destinatário:").pack(pady=5)
        self.email_entry = ttk.Entry(self, width=50)
        self.email_entry.pack(pady=5)

        ttk.Label(self, text="Texto do Relatório:").pack(pady=5)
        self.texto_entry = tk.Text(self, height=6, width=50)
        self.texto_entry.pack(pady=5)

        ttk.Button(self, text="Gerar e Enviar", command=self.gerar_e_enviar).pack(pady=10)

    def gerar_e_enviar(self):
        email = self.email_entry.get()
        texto = self.texto_entry.get("1.0", tk.END).strip()

        if not email or not texto:
            messagebox.showerror("Erro", "Preencha todos os campos.")
            return

        pdf = PDFRelatorio()
        pdf.adicionar_texto(texto)

        nome_arquivo = f"relatorio_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        caminho_pdf = os.path.join(os.getcwd(), nome_arquivo)
        pdf.salvar(caminho_pdf)

        enviar_email(email, "Relatório Gerado", "Segue em anexo o relatório solicitado.", caminho_pdf)
        messagebox.showinfo("Sucesso", f"Relatório enviado para {email}.")

if __name__ == "__main__":
    app = App()
    app.mainloop()
