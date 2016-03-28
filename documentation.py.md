# python-nuclos

Eine Python Bibliothek für die REST API von [Nuclos](http://www.nuclos.de/).

Der Quellcode kann von [Github](https://github.com/saierd/python-nuclos) heruntergeladen werden. Es wird
mindestens Nuclos 4.3 benötigt, da mit dieser Version die aktuelle Variante der API eingeführt wurde. Durch Änderungen
an der API sind leider nicht alle Nuclos Versionen kompatibel. Eine genaue Aufstellung der Nuclos Version und der
dazu passenden Bibliotheksversion finden Sie im Readme.

Außerdem wird mindestens Python 3.3 benötigt, Python 2 wird nicht unterstützt.

    #

Die Datei `nuclos.py` sollte sich im selben Ordner befinden, wie das Python Script, das sie verwenden soll.

    from nuclos import NuclosAPI

Um die Verbindung mit einem Nuclos Server herzustellen werden die Verbindungsdaten aus einer `ini`-Datei gelesen. In
der im Quellcode enthaltenen `default.ini` sind alle verfügbaren Parameter und ihre Standardwerte angegeben.

    nuclos = NuclosAPI("settings.ini")

## Businessobjekte

    #

Nun kann auf die Businessobjekte zugegriffen werden. Am einfachsten geht das, indem der Name eines Businessobjekes als
Eigenschaft der Klasse `NuclosAPI` verwendet wird.

Dabei ist die Groß- und Kleinschreibung egal. Ein Leerzeichen im Namen eines Businessobjektes kann durch einen
Unterstrich ersetzt werden.

    customer_bo = nuclos.customer
                = nuclos["customer"]
                = nuclos.get_business_object_by_name("customer")
                = nuclos.get_business_object(<bo_meta_id>)

    nuclos.business_objects             # = [<customer_bo>, ...]

Mit der `get` Methode kann eine bestimmte Instanz geladen werden.

    customer = customer_bo.get(<bo_id>)

Mit der `list` Methode erhält man eine Liste der Instanzen eines Businessobjektes.

    for customer in customer_bo.list():
        print(customer.title)

Mit verschiedenen Argumenten kann man das Verhalten der Methode beeinflussen und bspw. das Ergebnis sortieren kann.

Diese Argumente werden auch von allen unten angegebenen Varianten von `list` und `search` akzeptiert.

    customer_bo.list(offset=10, limit=20)

    customer_bo.list(sort=customer_bo.meta.city)
    customer_bo.list(sort="city")

Mit dem Parameter `where` werden auch beliebige Filter unterstützt. Es gibt derzeit allerdings keine einfache
Möglichkeit, diese aufzubauen. Stattdessen muss ein entsprechender String von Hand aufgebaut werden. Weitere
Informationen zum Aufbau der Filter erhalten Sie im [Nuclos Wiki](http://wiki.nuclos.de/display/Entwicklung/4.+Businessobjekte+%28BO%29+lesen).

    where_expression = "{} = 'john@doe.com'".format(customer_bo.meta.email.bo_attr_id)
    customer_bo.list(where=where_expression)

Dabei ist zu beachten, dass die `list` Methode nur einen Teil der Ergebnisse zurückliefert (nämlich gerade so viele,
wie durch den Parameter `limit` angefordert wurden). Um eine vollständige Liste zu erhalten, kann die Methode `list_all`
verwendet werden.

    customer_bo.list_all()

Die `search` Methode sucht nach Instanzen, in denen ein bestimmter Text vorkommt. Dabei werden wiederum  nur so viele
Ergebnisse zurückgegeben, wie durch den Parameter `limit` angegeben wurde. Entsprechend gibt es auch eine Methode
`search_all`, die die vollständige Liste zurückgibt.

    customers = customer_bo.search("Doe")
              = customer_bo.search_all("Doe")

Für `list` und `search` gibt es auch entsprechende Methoden, die nur den ersten Treffer zurückgeben.

    customer = customer_bo.get_one()
             = customer_bo.search_one("Doe")

Die `create` Methode erzeugt eine neue Instanz. Diese wird nicht in Nuclos gespeichert, bis die `save` Methode
aufgerufen wird. In dieser Zeit kann die Instanz nur eingeschränkt verwendet werden.

    new_customer = customer_bo.create()
    new_customer.name = "John Doe"
    new_customer.save()

## Instanzen von Businessobjekten

    #

Der Titel einer Instanz kann über die Eigenschaft `title` ausgelesen werden.

    customer.title                      # = "John Doe"

Die Attribute eines Instanz können gelesen werden, wie oben die Businessobjekte aus dem API Objekt.

Auch hier ist die Groß- und Kleinschreibung egal. Leerzeichen können wieder durch einen Unterstrich ersetzt werden.

    email = customer.email
          = customer["email"]
          = customer.get_attribute_by_name("email")
          = customer.get_attribute(<bo_attr_id>)

### Verändern von Daten

    #

Nach dem selben Prinzip können den Attributen neue Werte zugewiesen werden.

    customer.email = "john@doe.com"
    customer["email"] = "john@doe.com"
    customer.set_attribute_by_name("email", "john@doe.com")
    customer.set_attribute(<bo_attr_id>, "john@doe.com")

Veränderte Werte von Attributen lassen sich auf der lokalen Instanz sofort wieder auslesen, werden aber erst durch
einen Aufruf der `save` Methode auf dem Nuclos Server abgespeichert.

    customer.save()

Die `refresh` Methode sorgt dafür, dass die Daten der Instanz neu vom Server geladen werden. Das ist normalerweise nur
dann nötig, wenn ein anderer Benutzer die selbe Instanz zwischenzeitlich verändert hat.

Der Aufruf verwirft außerdem alle ungespeicherten Änderungen von Attributen.

    customer.refresh()

Die `delete` Methode löscht die Instanz.

    customer.delete()

### Referenzfelder

    #

Referenzierte Objekte können wie normale Attribute verwendet werden. Das zurückgegebene Object ist wieder eine Instanz
eines Businessobjektes und kann genau so verwendet werden.

    print(order.customer.name)

Referenzfelder können wie normale Felder verändert werden. Dabei kann eine Instanz übergeben werden, auf die das
Referenzfeld zeigen soll.

    john_doe = customer_bo.search_one("John Doe")
    order.customer = john_doe
    order.save()

Durch Zuweisen von `None` kann die Referenz entfernt werden.

### Unterformulare

    #

Daten aus Unterformularen können nach dem selben Prinzip geladen werden wie Attribute.

Dabei muss der Name des Businessobjektes verwendet werden, das die Einträge des Unterformulars bildet. Im Beispiel
hat das Businessobjekt der Positionen den Namen `order position`.

Falls es sowohl ein Attribut als auch ein Unterformular mit dem selben Namen gibt, geben die ersten beiden
Möglichkeiten den Wert des Attributes zurück.

    positions = order.order_position
              = order["order position"]
              = order.get_dependencies_by_name("order_position")
              = order.get_dependencies(<dependency_id>)

    for pos in positions:
        print(pos.title)

Setzt man `create_` vor den Namen des Unterformulars erhält man eine Methode, die einen neuen Eintrag in einem
Unterformular erzeugt.

    new_position = order.create_order_position()
                 = order.create_dependency_by_name("order position")
    new_position.article = ...
    new_position.save()

### Status

    #

Man kann den aktuellen Status einer Instanz über folgende spezielle Attribute auslesen:

    john_doe.current_state_name         # = "Active"
    john_doe.current_state_number       # = 10

Man kann den Status auch ändern, wahlweise über dessen Nummer oder Namen.

Dabei ist zu beachten, dass die Instanz automatisch aktualisiert wird. Nicht gespeicherte Änderungen gehen
dabei verloren.

    john_doe.change_to_state(99)
    john_doe.change_to_state_by_name("Inactive")

### Aktionen

    #

Die Aktion einer Instanz kann ebenfalls über ein spezielles Attribut ausgelesen werden:

    john_doe.process                    # = "Business Client"

Man kann die Aktion auch verändern. Im Gegensatz zur Änderung des Status, muss die Instanz dabei explizit gespeichert
werden.

    john_doe.set_process("Individual Client")
    john_doe.save()

## Metadaten

    #

Die `meta` Eigenschaft der Klasse `BusinessObject` (und auch von Instanzen) enthält einige Metadaten.

    customer_bo.meta.name               # = "Customer"
    customer_bo.meta.bo_meta_id

### Attribute

    #

Auch die Metadaten von Attributen können ausgelesen werden.

    email_attr = customer_bo.meta.email
               = customer_bo.meta["email"]
               = customer_bo.meta.get_attribute_by_name("email")
               = customer_bo.meta.get_attribute(<bo_attr_id>)

    customer_bo.meta.attributes         # = [<email_attr>, ...]

    email_attr.name                     # = "E-Mail"
    email_attr.bo_attr_id
    email_attr.type                     # = "String"
    email_attr.is_writeable
    email_attr.is_reference

## Exceptions

Die Bibliothek wirft im Falle von Fehlern verschiedene Exceptions, die alle von der Klasse `NuclosException` erben.

Falls der Login am Nuclos Server fehlschlägt oder dem angemeldeten Benutzer die Rechte für eine bestimmte Aktion fehlen
wird eine `NuclosAuthenticationException` geworfen.

Fall einem Attribut ein falscher Wert zugewiesen wird, wird eine `NuclosValueException` geworfen.

Wenn die verwendete Version des Nuclos Servers ein bestimmtes Feature nicht unterstützt wird eine
`NuclosVersionException` geworfen. 

Im Falle von HTTP Fehlern wirft die Bibliothek eine `NuclosHTTPException`. Diese hat die Eigenschaften `code` und
`reason`, die den empfangenen HTTP Statuscode bzw. die dazugehörige Beschreibung enthalten.
