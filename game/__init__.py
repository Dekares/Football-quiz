"""Çok-kişilik oyun paketi.

Alt modüller:
  - store:      Lobi kayıt defteri (in-memory) + thread-safe erişim.
  - lobby:      Lobby, Player dataclass'ları ve state makinesi.
  - matchmaking: Zorluğa göre kulüp çifti seçimi.
  - questions:  Soru üretimi (ortak oyuncu + çeldiriciler) ve cevap doğrulama.
  - sockets:    Flask-SocketIO event handler'ları (app.py tarafından register edilir).
"""
