# screen_analyzer.py

import pytesseract
from PIL import ImageGrab  # Pillow ImageGrab pour prendre des captures d'écran
import os  # Utilisé si on sauvegarde temporairement l'image pour débug
import time  # Utilisé dans le bloc de test en bas

# --- Configuration INDISPENSABLE pour Tesseract sur Windows ---
# Décommente la ligne suivante et adapte le chemin vers l'endroit EXACT
# où tu as installé Tesseract OCR sur ta machine.
# Le chemin par défaut est souvent C:\Program Files\Tesseract-OCR\tesseract.exe
# Si tu ne fais pas ça et que Tesseract n'est pas dans ton PATH système, ça ne marchera pas.
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


# ↑↑↑ VÉRIFIE ET ADAPTE CE CHEMIN SI NÉCESSAIRE ↑↑↑


def capture_and_ocr_primary_screen(language='fra+eng'):
    """
    Prend une capture de l'écran principal, effectue l'OCR et retourne le texte extrait.

    :param language: Langue(s) à utiliser pour l'OCR (ex: 'fra', 'eng', 'fra+eng').
    :return: Le texte extrait de l'écran, ou None en cas d'erreur.
    """
    print("INFO: Début de la capture d'écran...")
    try:
        screenshot = ImageGrab.grab()
        print("INFO: Capture d'écran prise.")

        # Optionnel: Sauvegarder l'image pour la vérifier (pour le débug)
        # screenshot_path = "debug_screenshot.png"
        # screenshot.save(screenshot_path)
        # print(f"INFO: Capture d'écran sauvegardée temporairement ici : {os.path.abspath(screenshot_path)}")

        print(f"INFO: Début de l'OCR avec la langue : {language}...")
        extracted_text = pytesseract.image_to_string(screenshot, lang=language)
        print("INFO: OCR terminé.")

        # if os.path.exists(screenshot_path): # Si on a sauvegardé pour débug
        #     os.remove(screenshot_path)

        if extracted_text and extracted_text.strip():
            # On affiche seulement un extrait pour ne pas surcharger la console si c'est long
            print(f"INFO: Texte extrait (premiers 300 caractères): \n{extracted_text.strip()[:300]}...")
            return extracted_text.strip()
        else:
            print("INFO: Aucun texte n'a pu être extrait par l'OCR ou le texte est vide.")
            return None

    except FileNotFoundError as e_tesseract_fnf:
        print(f"ERREUR CRITIQUE: Tesseract OCR introuvable. {e_tesseract_fnf}")
        print("   Vérifiez que Tesseract OCR est bien installé sur votre système.")
        print(f"   Vérifiez que la ligne 'pytesseract.pytesseract.tesseract_cmd' dans screen_analyzer.py")
        print(
            f"   pointe bien vers votre fichier 'tesseract.exe'. Actuellement: '{pytesseract.pytesseract.tesseract_cmd}'")
        print("   Lien pour installer Tesseract (Windows): https://github.com/UB-Mannheim/tesseract/wiki")
        return None
    except Exception as e_ocr:
        print(f"ERREUR: Une erreur est survenue dans capture_and_ocr_primary_screen: {e_ocr}")
        return None


# Ce bloc s'exécute seulement si tu lances screen_analyzer.py directement
if __name__ == '__main__':
    print("--- Test direct de screen_analyzer.py ---")

    # Important: Vérifie que le chemin vers tesseract.exe est correct ci-dessus !
    # Si pytesseract.tesseract_cmd n'est pas bien configuré, le test échouera.

    print("INFO: La capture d'écran et l'OCR auront lieu dans 5 secondes...")
    print("INFO: Assurez-vous d'avoir une fenêtre avec du texte visible au premier plan.")
    time.sleep(5)

    # Tu peux changer la langue ici pour tester, par exemple 'fra', 'eng', ou 'fra+eng'
    # Assure-toi que les packs de langue correspondants sont installés avec Tesseract.
    extracted_text_from_screen = capture_and_ocr_primary_screen(language='fra')

    print("\n--- RÉSULTAT DU TEST ---")
    if extracted_text_from_screen:
        print("Texte extrait de l'écran :\n")
        print(extracted_text_from_screen)
    else:
        print("Aucun texte n'a été extrait ou une erreur s'est produite.")
        print("Vérifiez les messages d'erreur ci-dessus, notamment concernant Tesseract.")
    print("--- Fin du test ---")