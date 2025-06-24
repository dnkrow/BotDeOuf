# web_utils.py

from duckduckgo_search import DDGS

def perform_sync_ddg_search(search_query, num_results=3):
    """
    Effectue une recherche web synchrone avec DuckDuckGo.
    Retourne une liste de résultats ou une liste vide en cas d'erreur.
    """
    try:
        # Ajout de "récent" pour essayer d'obtenir des informations plus actuelles
        with DDGS(timeout=10) as ddgs:
            results = ddgs.text(f"{search_query} récent", max_results=num_results)
            return results if results else []
    except Exception as e_ddgs:
        print(f"Erreur pendant la recherche DuckDuckGo: {e_ddgs}")
        return []

if __name__ == '__main__':
    # Petit test simple si on exécute ce fichier directement
    print("Test de la recherche web...")
    results = perform_sync_ddg_search("dernières nouvelles tech")
    if results:
        for i, res in enumerate(results):
            print(f"\nRésultat {i+1}:")
            print(f"  Titre: {res.get('title')}")
            print(f"  Lien: {res.get('href')}")
            print(f"  Extrait: {res.get('body')[:150]}...")
    else:
        print("Aucun résultat trouvé ou erreur.")