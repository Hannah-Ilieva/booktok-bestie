def recommend_books(books, preferred_mood, preferred_tropes):
    preferred_mood = preferred_mood.casefold()
    preferred_tropes = {
        trope.casefold().strip()
        for trope in preferred_tropes
    }

    scored_books = []

    for book in books:
        if book["status"] != "Want to Read":
            continue

        book_mood = (book["mood"] or "").casefold()
        book_tropes = {
            trope.casefold().strip()
            for trope in (book["tropes"] or "").split(",")
            if trope.strip()
        }

        score = 0

        if book_mood == preferred_mood:
            score += 2

        score += len(book_tropes & preferred_tropes)

        if score > 0:
            scored_books.append((score, book))

    scored_books.sort(key=lambda item: item[0], reverse=True)

    return [book for score, book in scored_books]