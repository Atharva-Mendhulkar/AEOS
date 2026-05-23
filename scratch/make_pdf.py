from reportlab.pdfgen import canvas
c = canvas.Canvas("test_payloads/system_summary.pdf")
c.drawString(100, 750, "AEOS System Summary Document")
c.drawString(100, 730, "Severity: Critical")
c.drawString(100, 710, "Multiple CPU exhaustion events detected across frontend pods.")
c.drawString(100, 690, "Memory usage climbed to 99% before out-of-memory kill.")
c.save()
