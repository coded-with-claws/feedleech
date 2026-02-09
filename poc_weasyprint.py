base_url = "https://slashdot.org/story/22/08/18/1352216/japan-wants-young-people-to-drink-more-alcohol"

from weasyprint import HTML

try:
    HTML(base_url).write_pdf("slashdotarticle.pdf")
except Exception as e:
    print(f"Error processing {base_url}: {str(e)}")


